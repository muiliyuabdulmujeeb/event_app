from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EventNotFoundError,
    RegistrationConflictError,
    RegistrationNotFoundError,
    StaffAccessForbiddenError,
    StaffAccountNotFoundError,
    StaffNotificationNotFoundError,
    StaffOperationConflictError,
    StaffOperationValidationError,
)
from app.core.security import utc_now
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccount, StaffRole
from app.repositories.event_repository import EventRepository
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import (
    StaffAccessConfigResponse,
    StaffAccountDetailResponse,
    StaffAccountUpdateRequest,
    StaffCheckInResponse,
    StaffNotificationListResponse,
    StaffNotificationReadResponse,
    StaffNotificationResponse,
    StaffRegistrationCustomFieldValueResponse,
    StaffRegistrationEventSummary,
    StaffRegistrationPaymentSummary,
    StaffRegistrationResult,
    StaffRegistrationSearchResponse,
    StaffSelectedEventSummary,
)


@dataclass
class StaffService:
    session: AsyncSession

    def __post_init__(self) -> None:
        self.repository = StaffRepository(self.session)
        self.event_repository = EventRepository(self.session)

    async def search_registrations(
        self,
        *,
        actor: StaffAccount,
        reg_id: str | None,
        email: str | None,
    ) -> StaffRegistrationSearchResponse:
        if bool(reg_id) == bool(email):
            raise StaffOperationValidationError("Provide exactly one of reg_id or email.")

        account = await self._load_account_with_access(actor.id)

        if reg_id is not None:
            registration = await self.repository.get_registration_by_reg_id(reg_id)
            if registration is None:
                raise RegistrationNotFoundError("No registration found for the provided reg_id.")
            self._ensure_registration_access(account, registration)
            registrations = [registration]
        else:
            assert email is not None
            registrations = list(await self.repository.list_registrations_by_email(email))
            accessible = [registration for registration in registrations if self._can_access_event(account, registration.event_id)]
            if not accessible and registrations:
                raise StaffAccessForbiddenError()
            registrations = accessible

        capacity_override_counts = await self.event_repository.list_capacity_override_counts(
            list({registration.event_id for registration in registrations})
        )

        return StaffRegistrationSearchResponse(
            registrations=[
                self._build_registration_result(
                    registration,
                    capacity_override_count=capacity_override_counts.get(registration.event_id, 0),
                )
                for registration in registrations
            ],
            total=len(registrations),
        )

    async def check_in_registration(self, *, actor: StaffAccount, reg_id: str) -> StaffCheckInResponse:
        account = await self._load_account_with_access(actor.id)
        registration = await self._load_registration_with_access(account, reg_id)

        if registration.state != RegistrationState.CONFIRMED:
            raise RegistrationConflictError("Only confirmed registrations can be checked in.")
        if registration.is_checked_in:
            raise RegistrationConflictError("This registration has already been checked in.")

        registration.is_checked_in = True
        registration.checked_in_at = utc_now()
        await self.session.flush()
        return StaffCheckInResponse(
            reg_id=registration.reg_id,
            state=registration.state,
            is_checked_in=registration.is_checked_in,
            checked_in_at=registration.checked_in_at,
        )

    async def uncheck_in_registration(self, *, actor: StaffAccount, reg_id: str) -> StaffCheckInResponse:
        account = await self._load_account_with_access(actor.id)
        registration = await self._load_registration_with_access(account, reg_id)

        if not registration.is_checked_in:
            raise RegistrationConflictError("This registration is not currently checked in.")

        registration.is_checked_in = False
        registration.checked_in_at = None
        await self.session.flush()
        return StaffCheckInResponse(
            reg_id=registration.reg_id,
            state=registration.state,
            is_checked_in=registration.is_checked_in,
            checked_in_at=registration.checked_in_at,
        )

    async def list_unread_notifications(self, *, actor: StaffAccount) -> StaffNotificationListResponse:
        notifications = await self.repository.list_unread_notifications(actor.id)
        payload = [
            StaffNotificationResponse(
                id=notification.id,
                title=notification.title,
                body=notification.body,
                is_read=notification.is_read,
                created_at=notification.created_at,
            )
            for notification in notifications
        ]
        return StaffNotificationListResponse(notifications=payload, total=len(payload))

    async def mark_notification_read(
        self,
        *,
        actor: StaffAccount,
        notification_id: str,
    ) -> StaffNotificationReadResponse:
        notification = await self.repository.get_staff_notification(notification_id, actor.id)
        if notification is None:
            raise StaffNotificationNotFoundError("Staff notification not found.")

        notification.is_read = True
        await self.session.flush()
        return StaffNotificationReadResponse(id=notification.id, is_read=notification.is_read)

    async def get_staff_account_detail(self, staff_id: str) -> StaffAccountDetailResponse:
        account = await self._load_account_with_access(staff_id)
        return self._build_staff_account_detail(account)

    async def update_staff_account(
        self,
        *,
        staff_id: str,
        payload: StaffAccountUpdateRequest,
    ) -> StaffAccountDetailResponse:
        account = await self._load_account_with_access(staff_id)
        if payload.email is not None:
            account.email = payload.email
        if payload.role is not None:
            account.role = payload.role
        if payload.is_active is not None:
            account.is_active = payload.is_active

        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise StaffOperationConflictError("The staff account could not be updated because it conflicts with existing data.") from exc

        return self._build_staff_account_detail(account)

    async def set_staff_access_mode(
        self,
        *,
        staff_id: str,
        mode: StaffAccessMode,
    ) -> StaffAccessConfigResponse:
        account = await self._load_account_with_access(staff_id)
        await self.repository.set_access_mode(account, mode)
        if mode == StaffAccessMode.ALL_EVENTS:
            for access_entry in list(account.event_access_entries):
                await self.repository.remove_event_access(access_entry)
            account.event_access_entries = []
        return self._build_access_config(account)

    async def add_staff_event_access(self, *, staff_id: str, event_id: str) -> StaffAccessConfigResponse:
        account = await self._load_account_with_access(staff_id)
        if account.access_mode_record is None or account.access_mode_record.mode != StaffAccessMode.SELECTED_EVENTS:
            raise StaffOperationValidationError("Event-specific access can only be modified when access mode is selected_events.")

        event = await self.repository.get_event(event_id)
        if event is None:
            raise EventNotFoundError("Event not found.")

        existing = await self.repository.get_event_access(staff_id, event_id)
        if existing is not None:
            raise StaffOperationConflictError("This event is already in the staff access list.")

        try:
            await self.repository.add_event_access(staff_id, event_id)
        except IntegrityError as exc:
            await self.session.rollback()
            raise StaffOperationConflictError("This event is already in the staff access list.") from exc

        account = await self._load_account_with_access(staff_id)
        return self._build_access_config(account)

    async def remove_staff_event_access(self, *, staff_id: str, event_id: str) -> StaffAccessConfigResponse:
        account = await self._load_account_with_access(staff_id)
        access = await self.repository.get_event_access(staff_id, event_id)
        if access is None:
            raise StaffOperationValidationError("This event is not currently in the staff access list.")

        await self.repository.remove_event_access(access)
        account = await self._load_account_with_access(staff_id)
        return self._build_access_config(account)

    async def _load_account_with_access(self, staff_id: str) -> StaffAccount:
        account = await self.repository.get_by_id_with_access(staff_id)
        if account is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        return account

    async def _load_registration_with_access(self, account: StaffAccount, reg_id: str) -> Registration:
        registration = await self.repository.get_registration_by_reg_id(reg_id)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")
        self._ensure_registration_access(account, registration)
        return registration

    def _ensure_registration_access(self, account: StaffAccount, registration: Registration) -> None:
        if not self._can_access_event(account, registration.event_id):
            raise StaffAccessForbiddenError()

    def _can_access_event(self, account: StaffAccount, event_id: str) -> bool:
        if account.role == StaffRole.ADMIN:
            return True

        mode = account.access_mode_record.mode if account.access_mode_record is not None else StaffAccessMode.ALL_EVENTS
        if mode == StaffAccessMode.ALL_EVENTS:
            return True

        return any(access_entry.event_id == event_id for access_entry in account.event_access_entries)

    def _build_registration_result(
        self,
        registration: Registration,
        *,
        capacity_override_count: int,
    ) -> StaffRegistrationResult:
        custom_field_values = [
            StaffRegistrationCustomFieldValueResponse(
                label=field_value.field_definition.label,
                value=field_value.value,
            )
            for field_value in sorted(
                registration.field_values,
                key=lambda value: value.field_definition.display_order,
            )
        ]
        payment = None
        if registration.payment is not None:
            payment = StaffRegistrationPaymentSummary(
                status=registration.payment.status,
                amount_paid=registration.payment.amount,
                currency=registration.payment.currency,
                paid_at=registration.payment.paid_at,
            )

        return StaffRegistrationResult(
            reg_id=registration.reg_id,
            first_name=registration.first_name,
            last_name=registration.last_name,
            email=registration.email,
            state=registration.state,
            is_checked_in=registration.is_checked_in,
            checked_in_at=registration.checked_in_at,
            registered_at=registration.registered_at,
            is_batch=registration.batch_id is not None,
            custom_field_values=custom_field_values,
            event=StaffRegistrationEventSummary(
                id=registration.event.id,
                title=registration.event.title,
                event_date=registration.event.event_date,
                location=registration.event.location,
                is_free=registration.event.is_free,
                state=registration.event.state,
                capacity_override_count=capacity_override_count,
            ),
            payment=payment,
        )

    def _build_staff_account_detail(self, account: StaffAccount) -> StaffAccountDetailResponse:
        return StaffAccountDetailResponse(
            id=account.id,
            email=account.email,
            role=account.role.value,
            is_active=account.is_active,
            created_at=account.created_at,
            access_mode=(
                account.access_mode_record.mode
                if account.access_mode_record is not None
                else StaffAccessMode.ALL_EVENTS
            ),
            selected_events=[
                StaffSelectedEventSummary(id=entry.event.id, title=entry.event.title)
                for entry in account.event_access_entries
                if entry.event is not None
            ],
        )

    def _build_access_config(self, account: StaffAccount) -> StaffAccessConfigResponse:
        return StaffAccessConfigResponse(
            staff_id=account.id,
            access_mode=(
                account.access_mode_record.mode
                if account.access_mode_record is not None
                else StaffAccessMode.ALL_EVENTS
            ),
            selected_events=[
                StaffSelectedEventSummary(id=entry.event.id, title=entry.event.title)
                for entry in account.event_access_entries
                if entry.event is not None
            ],
        )
