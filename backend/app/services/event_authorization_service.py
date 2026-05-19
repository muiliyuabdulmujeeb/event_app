from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EventAuthorizationForbiddenError,
    EventAuthorizationNotFoundError,
    EventAuthorizationValidationError,
    EventNotFoundError,
    StaffAccountNotFoundError,
)
from app.core.security import utc_now
from app.models.event import Event
from app.models.staff import StaffAccount, StaffRole
from app.models.staff_event_authorization import StaffEventAuthorization
from app.repositories.event_repository import EventRepository
from app.repositories.staff_event_authorization_repository import StaffEventAuthorizationRepository
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import (
    EventAuthorizationListResponse,
    EventAuthorizationPermissionsResponse,
    EventAuthorizationResponse,
    EventAuthorizationRevokeResponse,
    EventAuthorizationUpdateRequest,
)


DELEGATED_PERMISSION_NAMES = frozenset(
    {
        "can_manage_exception_offers",
        "can_change_overflow_rule",
        "can_manage_manual_reviews",
        "can_requeue_registrations",
    }
)
ADMIN_PERMISSION_NAMES = frozenset(
    {
        "can_manage_exception_offers",
        "can_change_overflow_rule",
    }
)
STAFF_PERMISSION_NAMES = frozenset(
    {
        "can_manage_manual_reviews",
        "can_requeue_registrations",
    }
)


@dataclass
class EventAuthorizationService:
    session: AsyncSession

    def __post_init__(self) -> None:
        self.event_repository = EventRepository(self.session)
        self.staff_repository = StaffRepository(self.session)
        self.authorization_repository = StaffEventAuthorizationRepository(self.session)

    async def list_event_authorizations(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
    ) -> EventAuthorizationListResponse:
        await self._require_event_creator(actor=actor, event_id=event_id)
        authorizations = await self.authorization_repository.list_active_for_event(event_id)
        return EventAuthorizationListResponse(
            event_id=event_id,
            authorizations=[self._build_response(item) for item in authorizations],
        )

    async def upsert_event_authorization(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        account_id: str,
        payload: EventAuthorizationUpdateRequest,
    ) -> EventAuthorizationResponse:
        await self._require_event_creator(actor=actor, event_id=event_id)
        target_account = await self.staff_repository.get_by_id(account_id)
        if target_account is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        if target_account.id == actor.id:
            raise EventAuthorizationValidationError("The event creator cannot authorize themselves.")

        self._validate_target_permissions(target_account=target_account, payload=payload)

        authorization = await self.authorization_repository.get_by_event_and_staff(
            event_id=event_id,
            staff_id=account_id,
            for_update=True,
        )
        if authorization is None:
            authorization = StaffEventAuthorization(
                event_id=event_id,
                staff_id=account_id,
                granted_by_staff_id=actor.id,
            )
            await self.authorization_repository.create(authorization)

        authorization.can_manage_exception_offers = payload.can_manage_exception_offers
        authorization.can_change_overflow_rule = payload.can_change_overflow_rule
        authorization.can_manage_manual_reviews = payload.can_manage_manual_reviews
        authorization.can_requeue_registrations = payload.can_requeue_registrations
        authorization.granted_by_staff_id = actor.id
        authorization.revoked_by_staff_id = None
        authorization.revoked_at = None
        await self.session.flush()
        refreshed_authorization = await self.authorization_repository.get_by_event_and_staff(
            event_id=event_id,
            staff_id=account_id,
        )
        if refreshed_authorization is None:
            raise EventAuthorizationNotFoundError("Event authorization not found.")
        return self._build_response(refreshed_authorization)

    async def revoke_event_authorization(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        account_id: str,
    ) -> EventAuthorizationRevokeResponse:
        await self._require_event_creator(actor=actor, event_id=event_id)
        authorization = await self.authorization_repository.get_by_event_and_staff(
            event_id=event_id,
            staff_id=account_id,
            for_update=True,
        )
        if authorization is None or authorization.revoked_at is not None:
            raise EventAuthorizationNotFoundError("Event authorization not found.")

        authorization.can_manage_exception_offers = False
        authorization.can_change_overflow_rule = False
        authorization.can_manage_manual_reviews = False
        authorization.can_requeue_registrations = False
        authorization.revoked_by_staff_id = actor.id
        authorization.revoked_at = utc_now()
        await self.session.flush()
        return EventAuthorizationRevokeResponse(
            event_id=event_id,
            account_id=account_id,
            revoked=True,
        )

    async def is_event_creator(self, *, actor_id: str, event_id: str) -> bool:
        event = await self.event_repository.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError("Event not found.")
        return event.created_by == actor_id

    async def has_delegated_permission(
        self,
        *,
        actor_id: str,
        event_id: str,
        permission_name: str,
    ) -> bool:
        if permission_name not in DELEGATED_PERMISSION_NAMES:
            raise EventAuthorizationValidationError("Unknown delegated permission.")

        authorization = await self.authorization_repository.get_by_event_and_staff(
            event_id=event_id,
            staff_id=actor_id,
        )
        if authorization is None or authorization.revoked_at is not None:
            return False
        return bool(getattr(authorization, permission_name))

    async def require_overflow_rule_manager(self, *, actor: StaffAccount, event_id: str) -> Event:
        event = await self.event_repository.get_by_id(event_id, for_update=True)
        if event is None:
            raise EventNotFoundError("Event not found.")
        if actor.role != StaffRole.ADMIN:
            raise EventAuthorizationForbiddenError(
                "Only the event creator or a delegated admin can change the overflow rule for this event."
            )
        if event.created_by == actor.id:
            return event
        has_permission = await self.has_delegated_permission(
            actor_id=actor.id,
            event_id=event_id,
            permission_name="can_change_overflow_rule",
        )
        if not has_permission:
            raise EventAuthorizationForbiddenError(
                "Only the event creator or a delegated admin can change the overflow rule for this event."
            )
        return event

    async def _require_event_creator(self, *, actor: StaffAccount, event_id: str) -> Event:
        event = await self.event_repository.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError("Event not found.")
        if event.created_by != actor.id:
            raise EventAuthorizationForbiddenError("Only the event creator can manage authorizations for this event.")
        return event

    def _validate_target_permissions(
        self,
        *,
        target_account: StaffAccount,
        payload: EventAuthorizationUpdateRequest,
    ) -> None:
        selected_permissions = {
            permission_name
            for permission_name in DELEGATED_PERMISSION_NAMES
            if getattr(payload, permission_name)
        }
        if not selected_permissions:
            raise EventAuthorizationValidationError("At least one delegated permission must be granted.")

        if target_account.role == StaffRole.ADMIN:
            invalid_permissions = selected_permissions - ADMIN_PERMISSION_NAMES
            if invalid_permissions:
                raise EventAuthorizationValidationError(
                    "Only exception-offer and overflow permissions can be granted to admin accounts for this event."
                )
            return

        invalid_permissions = selected_permissions - STAFF_PERMISSION_NAMES
        if invalid_permissions:
            raise EventAuthorizationValidationError(
                "Only manual-review and requeue permissions can be granted to staff accounts for this event."
            )

    def _build_response(self, authorization: StaffEventAuthorization) -> EventAuthorizationResponse:
        if authorization.staff is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        return EventAuthorizationResponse(
            event_id=authorization.event_id,
            account_id=authorization.staff_id,
            role=authorization.staff.role,
            permissions=EventAuthorizationPermissionsResponse(
                can_manage_exception_offers=authorization.can_manage_exception_offers,
                can_change_overflow_rule=authorization.can_change_overflow_rule,
                can_manage_manual_reviews=authorization.can_manage_manual_reviews,
                can_requeue_registrations=authorization.can_requeue_registrations,
            ),
            granted_by_staff_id=authorization.granted_by_staff_id,
            updated_at=authorization.updated_at,
        )
