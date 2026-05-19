from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    EventNotFoundError,
    ManualReviewCaseConflictError,
    ManualReviewCaseForbiddenError,
    ManualReviewCaseNotFoundError,
    ManualReviewCaseValidationError,
    RegistrationConflictError,
    RegistrationNotFoundError,
    StaffAccountNotFoundError,
)
from app.core.security import utc_now
from app.models.manual_review_case import ManualReviewCase, ManualReviewCaseStatus, ManualReviewCaseType
from app.models.payment import Payment, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccount, StaffRole
from app.models.waitlist_promotion_offer import WaitlistPromotionOfferStatus
from app.repositories.manual_review_repository import ManualReviewCaseFilters, ManualReviewRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.staff_repository import StaffRepository
from app.schemas.email import EmailMessage
from app.schemas.manual_review import (
    ManualReviewCaseListResponse,
    ManualReviewCaseResponse,
    ManualReviewCaseUpdateRequest,
    RegistrationPaymentInitializationResponse,
    RequeueRegistrationRequest,
    RequeueRegistrationResponse,
)
from app.services.event_authorization_service import EventAuthorizationService
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService


@dataclass(frozen=True)
class RequeueRegistrationResult:
    response: RequeueRegistrationResponse
    email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass
class ManualReviewService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = ManualReviewRepository(self.session)
        self.registration_repository = RegistrationRepository(self.session)
        self.staff_repository = StaffRepository(self.session)
        self.authorization_service = EventAuthorizationService(self.session)
        self.payment_service = PaymentService(self.session, self.settings)
        self.notification_service = NotificationService(self.session, self.settings)

    async def list_cases(
        self,
        *,
        actor: StaffAccount,
        filters: ManualReviewCaseFilters,
    ) -> ManualReviewCaseListResponse:
        account = await self._load_actor(actor.id)
        if filters.event_id is not None and not await self._can_manage_manual_reviews(account, filters.event_id):
            raise ManualReviewCaseForbiddenError("You do not have permission to access manual review cases for this event.")

        cases = await self.repository.list_cases(filters)
        accessible_cases = [case for case in cases if await self._can_access_case(account, case)]
        return ManualReviewCaseListResponse(
            cases=[self._build_case_response(case) for case in accessible_cases],
            total=len(accessible_cases),
        )

    async def get_case(self, *, actor: StaffAccount, case_id: str) -> ManualReviewCaseResponse:
        account = await self._load_actor(actor.id)
        case = await self.repository.get_case_by_id(case_id)
        if case is None:
            raise ManualReviewCaseNotFoundError("Manual review case not found.")
        if not await self._can_access_case(account, case):
            raise ManualReviewCaseForbiddenError("You do not have permission to access this manual review case.")
        return self._build_case_response(case)

    async def update_case(
        self,
        *,
        actor: StaffAccount,
        case_id: str,
        payload: ManualReviewCaseUpdateRequest,
    ) -> ManualReviewCaseResponse:
        account = await self._load_actor(actor.id)
        case = await self.repository.get_case_by_id(case_id, for_update=True)
        if case is None:
            raise ManualReviewCaseNotFoundError("Manual review case not found.")
        if not await self._can_access_case(account, case):
            raise ManualReviewCaseForbiddenError("You do not have permission to update this manual review case.")

        case.status = payload.status
        case.resolution_action = payload.resolution_action
        case.resolution_notes = payload.resolution_notes
        if payload.status in {ManualReviewCaseStatus.RESOLVED, ManualReviewCaseStatus.DISMISSED}:
            case.resolved_by_staff_id = account.id
            case.resolved_at = utc_now()
        else:
            case.resolved_by_staff_id = None
            case.resolved_at = None
        await self.session.flush()
        await self.session.refresh(case)
        return self._build_case_response(case)

    async def requeue_registration(
        self,
        *,
        actor: StaffAccount,
        reg_id: str,
        payload: RequeueRegistrationRequest,
    ) -> RequeueRegistrationResult:
        account = await self._load_actor(actor.id)
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id, for_update=True)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")
        if not await self._can_requeue_registration(account, registration.event_id):
            raise ManualReviewCaseForbiddenError("You do not have permission to requeue registrations for this event.")

        event = await self.registration_repository.lock_event(registration.event_id)
        if event is None:
            raise EventNotFoundError("Event not found.")
        if event.is_free:
            raise ManualReviewCaseValidationError("Only paid registrations can be requeued.")
        if registration.batch_id is not None:
            raise ManualReviewCaseValidationError("Batch registrations cannot be requeued individually.")
        if registration.state != RegistrationState.FAILED:
            raise ManualReviewCaseConflictError("Only failed registrations can be requeued.")
        if registration.is_checked_in:
            raise ManualReviewCaseConflictError("Checked-in registrations cannot be requeued.")

        current_payment = registration.payment
        if current_payment is not None and current_payment.status == PaymentStatus.PENDING:
            raise ManualReviewCaseConflictError("This registration already has an active payment attempt.")
        if current_payment is not None and current_payment.status == PaymentStatus.SUCCESSFUL:
            raise ManualReviewCaseConflictError(
                "This registration cannot be requeued because its latest payment attempt already succeeded."
            )

        if not self._can_override_capacity(registration):
            occupied_slots = await self.registration_repository.count_capacity_occupying_registrations(event.id)
            if event.capacity is not None and occupied_slots >= event.capacity:
                raise RegistrationConflictError("No capacity slot is currently available for this requeue.")

        case = await self.repository.get_open_case_for_registration(registration.id)
        if case is None:
            case = await self.repository.create_case(
                ManualReviewCase(
                    event_id=registration.event_id,
                    registration_id=registration.id,
                    payment_id=current_payment.id if current_payment is not None else None,
                    case_type=self._resolve_requeue_case_type(current_payment),
                    status=ManualReviewCaseStatus.OPEN,
                    summary=f"Requeue requested for registration {registration.reg_id}",
                    details=payload.reason,
                    created_by_system=False,
                    created_by_staff_id=account.id,
                )
            )

        payment = await self.payment_service.prepare_registration_payment(registration=registration, event=event)
        registration.state = RegistrationState.PENDING_PAYMENT
        if registration.waitlist_promotion_offer is not None:
            registration.waitlist_promotion_offer.payment = payment
            registration.waitlist_promotion_offer.gateway_checkout_url = None

        case.payment_id = payment.id
        case.status = ManualReviewCaseStatus.RESOLVED
        case.resolution_action = "requeue_registration"
        case.resolution_notes = payload.reason
        case.resolved_by_staff_id = account.id
        case.resolved_at = utc_now()
        await self.session.flush()

        email_messages: list[EmailMessage] = []
        if payload.notify_user:
            notification_result = await self.notification_service.dispatch_payment_retry_notification(
                registration=registration
            )
            email_messages = notification_result.email_messages

        return RequeueRegistrationResult(
            response=RequeueRegistrationResponse(
                reg_id=registration.reg_id,
                state=registration.state,
                manual_review_case_id=case.id,
                message="Registration requeued successfully.",
            ),
            email_messages=email_messages,
        )

    async def initialize_registration_payment(
        self,
        *,
        reg_id: str,
    ) -> RegistrationPaymentInitializationResponse:
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id, for_update=True)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")
        event = await self.registration_repository.lock_event(registration.event_id)
        if event is None:
            raise EventNotFoundError("Event not found.")
        if event.is_free:
            raise RegistrationConflictError("This registration does not require payment.")
        if registration.batch_id is not None:
            raise RegistrationConflictError("This payment link is not available for batch registrations.")
        if registration.state != RegistrationState.PENDING_PAYMENT:
            if registration.state == RegistrationState.CONFIRMED:
                raise RegistrationConflictError("This registration has already been paid.")
            raise RegistrationConflictError("This payment link is no longer active.")

        result = await self.payment_service.initialize_registration_payment_by_registration(
            registration=registration,
            event=event,
        )
        if registration.waitlist_promotion_offer is not None:
            registration.waitlist_promotion_offer.payment = registration.payment
            registration.waitlist_promotion_offer.gateway_checkout_url = result.checkout_url
            if registration.waitlist_promotion_offer.status != WaitlistPromotionOfferStatus.CANCELLED:
                registration.waitlist_promotion_offer.status = WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED
        await self.session.flush()
        return RegistrationPaymentInitializationResponse(
            checkout_url=result.checkout_url,
            payment_reference=result.payment_reference,
            message="Payment initialized successfully.",
        )

    async def create_late_payment_success_case(
        self,
        *,
        payment: Payment,
        paid_at: str | None,
    ) -> ManualReviewCase:
        existing_case = await self.repository.get_open_case_for_payment(payment.id)
        if existing_case is not None:
            return existing_case

        event_id = payment.registration.event_id if payment.registration is not None else payment.batch_registration.event_id
        registration_id = payment.registration.id if payment.registration is not None else None
        owner = payment.registration.reg_id if payment.registration is not None else payment.batch_id
        owner_label = "registration" if payment.registration is not None else "batch"
        paid_at_suffix = f" at {paid_at}" if paid_at is not None else ""
        return await self.repository.create_case(
            ManualReviewCase(
                event_id=event_id,
                registration_id=registration_id,
                payment_id=payment.id,
                case_type=ManualReviewCaseType.LATE_PAYMENT_SUCCESS,
                status=ManualReviewCaseStatus.OPEN,
                summary=f"Late payment success for {owner_label} {owner}",
                details=(
                    f"Payment reference {payment.payment_reference} reported success{paid_at_suffix} "
                    "after the original payment window had already been closed."
                ),
                created_by_system=True,
            )
        )

    async def _load_actor(self, actor_id: str) -> StaffAccount:
        account = await self.staff_repository.get_by_id_with_access(actor_id)
        if account is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        return account

    async def _can_access_case(self, account: StaffAccount, case: ManualReviewCase) -> bool:
        if account.role == StaffRole.ADMIN:
            return True
        if case.event_id is None:
            return False
        return await self._can_manage_manual_reviews(account, case.event_id)

    async def _can_manage_manual_reviews(self, account: StaffAccount, event_id: str) -> bool:
        if account.role == StaffRole.ADMIN:
            return True
        if not self._can_access_event(account, event_id):
            return False
        return await self.authorization_service.has_delegated_permission(
            actor_id=account.id,
            event_id=event_id,
            permission_name="can_manage_manual_reviews",
        )

    async def _can_requeue_registration(self, account: StaffAccount, event_id: str) -> bool:
        if account.role == StaffRole.ADMIN:
            return True
        if not self._can_access_event(account, event_id):
            return False
        return await self.authorization_service.has_delegated_permission(
            actor_id=account.id,
            event_id=event_id,
            permission_name="can_requeue_registrations",
        )

    def _can_access_event(self, account: StaffAccount, event_id: str) -> bool:
        mode = account.access_mode_record.mode if account.access_mode_record is not None else StaffAccessMode.ALL_EVENTS
        if mode == StaffAccessMode.ALL_EVENTS:
            return True
        return any(entry.event_id == event_id for entry in account.event_access_entries)

    def _resolve_requeue_case_type(self, payment: Payment | None) -> ManualReviewCaseType:
        if payment is None:
            return ManualReviewCaseType.PAYMENT_TIMEOUT_REQUEUE
        if payment.status == PaymentStatus.FAILED:
            return ManualReviewCaseType.PAYMENT_FAILURE_REQUEUE
        return ManualReviewCaseType.OTHER

    def _can_override_capacity(self, registration: Registration) -> bool:
        return bool(
            registration.exception_offer is not None and registration.exception_offer.capacity_override
        )

    def _build_case_response(self, case: ManualReviewCase) -> ManualReviewCaseResponse:
        return ManualReviewCaseResponse(
            id=case.id,
            event_id=case.event_id,
            registration_id=case.registration_id,
            reg_id=case.registration.reg_id if case.registration is not None else None,
            payment_id=case.payment_id,
            payment_reference=case.payment.payment_reference if case.payment is not None else None,
            case_type=case.case_type,
            status=case.status,
            summary=case.summary,
            details=case.details,
            created_by_system=case.created_by_system,
            created_by_staff_id=case.created_by_staff_id,
            assigned_to_staff_id=case.assigned_to_staff_id,
            resolved_by_staff_id=case.resolved_by_staff_id,
            resolution_action=case.resolution_action,
            resolution_notes=case.resolution_notes,
            created_at=case.created_at,
            updated_at=case.updated_at,
            resolved_at=case.resolved_at,
        )
