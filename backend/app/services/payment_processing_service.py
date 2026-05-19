from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import PaymentNotFoundError
from app.core.security import utc_now
from app.models.payment import Payment, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.waitlist_promotion_offer import WaitlistPromotionOfferStatus
from app.repositories.payment_repository import PaymentRepository
from app.schemas.email import EmailMessage
from app.services.email_templates import build_ticket_email_message
from app.services.manual_review_service import ManualReviewService
from app.services.notification_service import NotificationService


PAYMENT_SUCCESS_EVENT = "payment.success"
PAYMENT_FAILED_EVENT = "payment.failed"


@dataclass(frozen=True)
class PaymentProcessingResult:
    reference: str
    event_type: str
    status: PaymentStatus
    processed: bool
    registration_ids: list[str]
    ticket_email_messages: list[EmailMessage]


@dataclass
class PaymentProcessingService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = PaymentRepository(self.session)
        self.notification_service = NotificationService(self.session, self.settings)
        self.manual_review_service = ManualReviewService(self.session, self.settings)

    async def process_event(
        self,
        *,
        event_type: str,
        reference: str,
        paid_at: datetime | None = None,
    ) -> PaymentProcessingResult:
        payment = await self.repository.get_by_reference(reference, for_update=True)
        if payment is None:
            raise PaymentNotFoundError(f"Payment with reference '{reference}' was not found.")

        if payment.status == PaymentStatus.SUCCESSFUL:
            return PaymentProcessingResult(
                reference=reference,
                event_type=event_type,
                status=payment.status,
                processed=False,
                registration_ids=self._collect_registration_ids(payment),
                ticket_email_messages=[],
            )

        if payment.status == PaymentStatus.FAILED and event_type == PAYMENT_FAILED_EVENT:
            return PaymentProcessingResult(
                reference=reference,
                event_type=event_type,
                status=payment.status,
                processed=False,
                registration_ids=self._collect_registration_ids(payment),
                ticket_email_messages=[],
            )

        if payment.status == PaymentStatus.FAILED and event_type == PAYMENT_SUCCESS_EVENT:
            return await self._mark_successful_for_manual_review(payment, paid_at=paid_at or utc_now())

        if event_type == PAYMENT_SUCCESS_EVENT:
            return await self._mark_successful(payment, paid_at=paid_at or utc_now())
        if event_type == PAYMENT_FAILED_EVENT:
            return await self._mark_failed(payment)

        return PaymentProcessingResult(
            reference=reference,
            event_type=event_type,
            status=payment.status,
            processed=False,
            registration_ids=self._collect_registration_ids(payment),
            ticket_email_messages=[],
        )

    async def expire_stale_payments(self) -> list[PaymentProcessingResult]:
        cutoff = utc_now() - timedelta(minutes=self.settings.payment_timeout_minutes)
        stale_payments = await self.repository.list_expired_pending_payments(cutoff)
        results: list[PaymentProcessingResult] = []
        for payment in stale_payments:
            results.append(await self._mark_failed(payment))
        return results

    async def _mark_successful(
        self,
        payment: Payment,
        *,
        paid_at: datetime,
    ) -> PaymentProcessingResult:
        if not self._pending_owner_registrations(payment):
            return await self._mark_successful_for_manual_review(payment, paid_at=paid_at)

        payment.status = PaymentStatus.SUCCESSFUL
        payment.paid_at = paid_at

        affected_registrations = self._pending_owner_registrations(payment)
        for registration in affected_registrations:
            registration.state = RegistrationState.CONFIRMED
            if registration.waitlist_promotion_offer is not None:
                registration.waitlist_promotion_offer.status = WaitlistPromotionOfferStatus.PAID

        await self.session.flush()
        ticket_email_messages = [
            build_ticket_email_message(self.settings, event=registration.event, registration=registration)
            for registration in affected_registrations
        ]
        return PaymentProcessingResult(
            reference=payment.payment_reference,
            event_type=PAYMENT_SUCCESS_EVENT,
            status=payment.status,
            processed=True,
            registration_ids=[registration.id for registration in affected_registrations],
            ticket_email_messages=ticket_email_messages,
        )

    async def _mark_successful_for_manual_review(
        self,
        payment: Payment,
        *,
        paid_at: datetime,
    ) -> PaymentProcessingResult:
        payment.status = PaymentStatus.SUCCESSFUL
        payment.paid_at = paid_at
        if payment.registration is not None and payment.registration.waitlist_promotion_offer is not None:
            payment.registration.waitlist_promotion_offer.status = WaitlistPromotionOfferStatus.MANUAL_REVIEW
        await self.manual_review_service.create_late_payment_success_case(
            payment=payment,
            paid_at=paid_at.isoformat(),
        )
        await self.notification_service.notify_manual_payment_review(
            payment=payment,
            paid_at=paid_at.isoformat(),
        )
        await self.session.flush()
        return PaymentProcessingResult(
            reference=payment.payment_reference,
            event_type=PAYMENT_SUCCESS_EVENT,
            status=payment.status,
            processed=True,
            registration_ids=self._collect_registration_ids(payment),
            ticket_email_messages=[],
        )

    async def _mark_failed(self, payment: Payment) -> PaymentProcessingResult:
        payment.status = PaymentStatus.FAILED
        payment.paid_at = None

        affected_registrations = self._pending_owner_registrations(payment)
        for registration in affected_registrations:
            registration.state = RegistrationState.FAILED
            if registration.waitlist_promotion_offer is not None:
                registration.waitlist_promotion_offer.status = WaitlistPromotionOfferStatus.FAILED

        await self.session.flush()
        return PaymentProcessingResult(
            reference=payment.payment_reference,
            event_type=PAYMENT_FAILED_EVENT,
            status=payment.status,
            processed=True,
            registration_ids=[registration.id for registration in affected_registrations],
            ticket_email_messages=[],
        )

    def _pending_owner_registrations(self, payment: Payment) -> list[Registration]:
        if payment.registration is not None:
            if payment.registration.state == RegistrationState.PENDING_PAYMENT:
                return [payment.registration]
            return []

        if payment.batch_registration is None:
            return []

        return [
            registration
            for registration in payment.batch_registration.registrations
            if registration.state == RegistrationState.PENDING_PAYMENT
        ]

    def _collect_registration_ids(self, payment: Payment) -> list[str]:
        if payment.registration is not None:
            return [payment.registration.id]
        if payment.batch_registration is None:
            return []
        return [registration.id for registration in payment.batch_registration.registrations]
