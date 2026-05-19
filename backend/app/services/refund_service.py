from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import utc_now
from app.core.exceptions import (
    RefundRequestConflictError,
    RefundRequestNotFoundError,
    RefundRequestValidationError,
    RegistrationConflictError,
    RegistrationNotFoundError,
)
from app.models.payment import PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestedBy, RefundRequestStatus
from app.models.registration import CancellationReason, Registration, RegistrationState
from app.models.staff import StaffAccount
from app.models.waitlist_promotion_offer import WaitlistPromotionOfferStatus
from app.repositories.refund_repository import RefundRepository
from app.repositories.registration_repository import RegistrationRepository
from app.schemas.email import EmailMessage
from app.schemas.notification import NotificationMethod
from app.schemas.refund import (
    AdminRefundRequestListResponse,
    AdminRefundRequestSummaryResponse,
    AdminRefundRequestUpdateRequest,
    AdminRefundRequestUpdateResponse,
    RefundRequestCreateRequest,
    RefundRequestCreateResponse,
    RegistrationCancellationRequest,
    RegistrationCancellationResponse,
)
from app.services.notification_service import NotificationService


ACTIVE_REFUND_REQUEST_STATUSES = {
    RefundRequestStatus.REQUESTED,
    RefundRequestStatus.APPROVED,
}

ALLOWED_REFUND_REQUEST_STATUS_TRANSITIONS: dict[RefundRequestStatus, set[RefundRequestStatus]] = {
    RefundRequestStatus.REQUESTED: {
        RefundRequestStatus.APPROVED,
        RefundRequestStatus.REJECTED,
        RefundRequestStatus.COMPLETED,
    },
    RefundRequestStatus.APPROVED: {
        RefundRequestStatus.REJECTED,
        RefundRequestStatus.COMPLETED,
    },
    RefundRequestStatus.REJECTED: set(),
    RefundRequestStatus.COMPLETED: set(),
}

DEFAULT_REFUND_APPROVED_TITLE = "Refund Approved"
DEFAULT_REFUND_REJECTED_TITLE = "Refund Rejected"
DEFAULT_REFUND_COMPLETED_TITLE = "Refund Completed"


@dataclass(frozen=True)
class RegistrationCancellationServiceResult:
    response: RegistrationCancellationResponse
    promoted_ticket_email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass(frozen=True)
class RefundRequestUpdateServiceResult:
    response: AdminRefundRequestUpdateResponse
    email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass
class RefundService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.registration_repository = RegistrationRepository(self.session)
        self.refund_repository = RefundRepository(self.session)
        self.notification_service = NotificationService(self.session, self.settings)

    async def cancel_registration(
        self,
        *,
        reg_id: str,
        payload: RegistrationCancellationRequest,
    ) -> RegistrationCancellationServiceResult:
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id, for_update=True)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")

        self._validate_cancellation_allowed(registration)
        released_from_confirmed = registration.state == RegistrationState.CONFIRMED
        previous_waitlist_position = registration.waitlist_position

        if registration.state == RegistrationState.PENDING_PAYMENT and registration.payment is not None:
            registration.payment.status = PaymentStatus.FAILED

        if (
            registration.waitlist_promotion_offer is not None
            and registration.waitlist_promotion_offer.status
            in {WaitlistPromotionOfferStatus.OFFERED, WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED}
        ):
            registration.waitlist_promotion_offer.status = WaitlistPromotionOfferStatus.CANCELLED

        registration.state = RegistrationState.CANCELLED
        registration.cancellation_reason = CancellationReason.USER_CANCELLED
        if previous_waitlist_position is not None:
            registration.was_waitlisted = True
            registration.previous_waitlist_position = previous_waitlist_position
            registration.waitlist_position = None

        await self.session.flush()
        if previous_waitlist_position is not None:
            await self._resequence_waitlist(registration.event_id)

        promoted_ticket_email_messages = await self.notification_service.promote_next_waitlisted_registration_if_needed(
            event=registration.event,
            released_from_confirmed=released_from_confirmed,
        )

        return RegistrationCancellationServiceResult(
            response=RegistrationCancellationResponse(
                reg_id=registration.reg_id,
                state=registration.state,
                was_waitlisted=registration.was_waitlisted,
                previous_waitlist_position=registration.previous_waitlist_position,
                cancellation_reason=registration.cancellation_reason,
                message="Registration cancelled successfully.",
            ),
            promoted_ticket_email_messages=promoted_ticket_email_messages,
        )

    async def create_refund_request(
        self,
        *,
        reg_id: str,
        payload: RefundRequestCreateRequest,
    ) -> RefundRequestCreateResponse:
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id, for_update=True)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")

        if registration.state != RegistrationState.CANCELLED:
            raise RefundRequestConflictError("Only cancelled registrations can request a refund.")
        if not await self.refund_repository.registration_has_successful_payment_history(registration.id):
            raise RefundRequestConflictError(
                "Refund requests are only available for registrations with successful payment history."
            )
        if any(refund_request.status in ACTIVE_REFUND_REQUEST_STATUSES for refund_request in registration.refund_requests):
            raise RefundRequestConflictError("An active refund request already exists for this registration.")
        if any(refund_request.status == RefundRequestStatus.COMPLETED for refund_request in registration.refund_requests):
            raise RefundRequestConflictError("Refund has already been completed for this registration.")

        refund_request = RefundRequest(
            registration_id=registration.id,
            status=RefundRequestStatus.REQUESTED,
            requested_by=RefundRequestedBy.PUBLIC,
            reason=payload.reason,
        )
        await self.refund_repository.create_refund_request(refund_request)
        await self.session.flush()
        return RefundRequestCreateResponse(
            refund_request_id=refund_request.id,
            reg_id=registration.reg_id,
            status=refund_request.status,
            requested_at=refund_request.requested_at,
            message="Refund request submitted successfully.",
        )

    async def list_refund_requests(
        self,
        *,
        status: RefundRequestStatus | None = None,
        event_id: str | None = None,
        reg_id: str | None = None,
    ) -> AdminRefundRequestListResponse:
        refund_requests = await self.refund_repository.list_refund_requests(
            status=status,
            event_id=event_id,
            reg_id=reg_id,
        )
        return AdminRefundRequestListResponse(
            items=[
                AdminRefundRequestSummaryResponse(
                    refund_request_id=refund_request.id,
                    reg_id=refund_request.registration.reg_id,
                    status=refund_request.status,
                    requested_at=refund_request.requested_at,
                    processed_at=refund_request.processed_at,
                )
                for refund_request in refund_requests
            ],
            total=len(refund_requests),
        )

    async def update_refund_request(
        self,
        *,
        refund_request_id: str,
        payload: AdminRefundRequestUpdateRequest,
        processed_by: StaffAccount,
    ) -> RefundRequestUpdateServiceResult:
        refund_request = await self.refund_repository.get_refund_request_by_id(refund_request_id, for_update=True)
        if refund_request is None:
            raise RefundRequestNotFoundError()

        self._validate_refund_request_transition(refund_request.status, payload.status)
        refund_request.status = payload.status
        refund_request.processed_by_staff_id = processed_by.id
        refund_request.processed_at = utc_now()
        refund_request.resolution_notes = payload.resolution_notes
        await self.session.flush()

        title = payload.title or self._default_refund_title(payload.status)
        dispatch_result = await self.notification_service.dispatch_refund_notification(
            registration=refund_request.registration,
            method=payload.notification_method,
            title=title,
            body=payload.message_body,
        )
        return RefundRequestUpdateServiceResult(
            response=AdminRefundRequestUpdateResponse(
                refund_request_id=refund_request.id,
                reg_id=refund_request.registration.reg_id,
                status=refund_request.status,
                processed_at=refund_request.processed_at,
                message="Refund request updated successfully.",
            ),
            email_messages=dispatch_result.email_messages,
        )

    async def _resequence_waitlist(self, event_id: str) -> None:
        waitlisted_registrations = await self.registration_repository.list_registrations_for_event(
            event_id,
            states=[RegistrationState.WAITLISTED],
            for_update=True,
        )
        for index, registration in enumerate(waitlisted_registrations, start=1):
            registration.waitlist_position = index
        await self.session.flush()

    def _validate_cancellation_allowed(self, registration: Registration) -> None:
        if registration.is_checked_in:
            raise RegistrationConflictError("Checked-in registrations cannot be cancelled.")
        if registration.state not in {
            RegistrationState.CONFIRMED,
            RegistrationState.PENDING_PAYMENT,
            RegistrationState.WAITLISTED,
        }:
            raise RegistrationConflictError("This registration cannot be cancelled in its current state.")

    def _validate_refund_request_transition(
        self,
        current_status: RefundRequestStatus,
        next_status: RefundRequestStatus,
    ) -> None:
        if next_status not in ALLOWED_REFUND_REQUEST_STATUS_TRANSITIONS[current_status]:
            raise RefundRequestValidationError(
                f"Invalid refund request transition from '{current_status.value}' to '{next_status.value}'."
            )

    def _default_refund_title(self, status: RefundRequestStatus) -> str:
        if status == RefundRequestStatus.APPROVED:
            return DEFAULT_REFUND_APPROVED_TITLE
        if status == RefundRequestStatus.REJECTED:
            return DEFAULT_REFUND_REJECTED_TITLE
        return DEFAULT_REFUND_COMPLETED_TITLE
