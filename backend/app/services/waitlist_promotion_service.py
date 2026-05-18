from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    RegistrationNotFoundError,
    StaffAccessForbiddenError,
    StaffAccountNotFoundError,
    StaffOperationForbiddenError,
    WaitlistPromotionConflictError,
    WaitlistPromotionExpiredError,
    WaitlistPromotionNotFoundError,
    WaitlistPromotionValidationError,
)
from app.core.security import utc_now
from app.models.event import OverflowRule
from app.models.payment import PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccount, StaffRole
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus
from app.repositories.notification_repository import NotificationRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.staff_repository import StaffRepository
from app.repositories.waitlist_promotion_repository import (
    ACTIVE_WAITLIST_PROMOTION_STATUSES,
    WaitlistPromotionRepository,
)
from app.schemas.email import EmailMessage
from app.schemas.waitlist_promotion import WaitlistPromotionRequest, WaitlistPromotionResponse
from app.services.email_templates import build_waitlist_promotion_offer_email_message
from app.services.payment_service import PaymentService


WAITLIST_PROMOTION_NOTIFICATION_TITLE = "Payment Slot Available"


@dataclass(frozen=True)
class WaitlistPromotionServiceResult:
    response: WaitlistPromotionResponse
    email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass(frozen=True)
class WaitlistPromotionInitializationResult:
    checkout_url: str


@dataclass(frozen=True)
class WaitlistPromotionExpiryResult:
    public_token: str
    reg_id: str
    status: WaitlistPromotionOfferStatus


@dataclass
class WaitlistPromotionService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.registration_repository = RegistrationRepository(self.session)
        self.staff_repository = StaffRepository(self.session)
        self.notification_repository = NotificationRepository(self.session)
        self.waitlist_promotion_repository = WaitlistPromotionRepository(self.session)
        self.payment_service = PaymentService(self.session, self.settings)

    async def promote_waitlisted_registration(
        self,
        *,
        actor: StaffAccount,
        reg_id: str,
        payload: WaitlistPromotionRequest,
    ) -> WaitlistPromotionServiceResult:
        account = await self._load_actor(actor.id)
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id, for_update=True)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")

        self._ensure_registration_access(account, registration)
        event = await self.registration_repository.lock_event(registration.event_id)
        if event is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")

        if registration.state != RegistrationState.WAITLISTED:
            raise WaitlistPromotionConflictError("Only waitlisted registrations can be promoted.")
        if event.is_free:
            raise WaitlistPromotionValidationError(
                "Only paid waitlisted registrations can be promoted into a payment offer."
            )
        if event.capacity is None or event.overflow_rule != OverflowRule.WAITLIST:
            raise WaitlistPromotionValidationError("This event does not support paid waitlist promotion.")

        available_slots = event.capacity - await self.registration_repository.count_capacity_occupying_registrations(
            event.id
        )
        if available_slots < 1:
            raise WaitlistPromotionConflictError("No capacity slot is currently available for this promotion.")

        existing_offer = await self.waitlist_promotion_repository.get_by_registration_id(
            registration.id,
            for_update=True,
        )
        if existing_offer is not None:
            raise WaitlistPromotionConflictError("This waitlisted registration has already been promoted.")

        offer_expires_at = self._resolve_offer_expiry(account=account, requested_expiry=payload.offer_expires_at)

        registration.state = RegistrationState.PENDING_PAYMENT
        registration.waitlist_position = None

        offer = WaitlistPromotionOffer(
            registration_id=registration.id,
            event_id=event.id,
            offered_by_staff_id=account.id,
            offer_expires_at=offer_expires_at,
            status=WaitlistPromotionOfferStatus.OFFERED,
        )
        await self.waitlist_promotion_repository.create_offer(offer)
        await self._resequence_waitlist(event.id)

        payment_action_url = self.build_payment_action_url(offer.public_token)
        notification_body = self._build_user_notification_body(
            event_title=event.title,
            payment_action_url=payment_action_url,
            offer_expires_at=offer.offer_expires_at,
        )
        await self.notification_repository.create_user_notification(
            reg_id=registration.reg_id,
            title=WAITLIST_PROMOTION_NOTIFICATION_TITLE,
            body=notification_body,
        )
        await self.session.flush()

        email_message = build_waitlist_promotion_offer_email_message(
            self.settings,
            event=event,
            registration=registration,
            payment_action_url=payment_action_url,
            offer_expires_at=offer.offer_expires_at,
        )
        return WaitlistPromotionServiceResult(
            response=WaitlistPromotionResponse(
                reg_id=registration.reg_id,
                state=registration.state,
                promotion_offer_status=offer.status,
                offer_expires_at=offer.offer_expires_at,
                payment_action_url=payment_action_url,
                message="Waitlisted attendee promoted successfully. Payment instructions have been sent.",
            ),
            email_messages=[email_message],
        )

    async def initialize_payment_offer(self, public_token: str) -> WaitlistPromotionInitializationResult:
        offer = await self.waitlist_promotion_repository.get_by_public_token(public_token, for_update=True)
        if offer is None:
            raise WaitlistPromotionNotFoundError("Waitlist promotion offer not found.")

        if utc_now() >= offer.offer_expires_at and offer.status in ACTIVE_WAITLIST_PROMOTION_STATUSES:
            await self._expire_offer(offer)
            raise WaitlistPromotionExpiredError()

        if offer.registration.state != RegistrationState.PENDING_PAYMENT:
            if offer.registration.state == RegistrationState.CONFIRMED:
                raise WaitlistPromotionConflictError("This payment offer has already been paid.")
            raise WaitlistPromotionConflictError("This payment offer is no longer active.")

        if offer.status in {
            WaitlistPromotionOfferStatus.EXPIRED,
            WaitlistPromotionOfferStatus.FAILED,
            WaitlistPromotionOfferStatus.CANCELLED,
            WaitlistPromotionOfferStatus.MANUAL_REVIEW,
        }:
            raise WaitlistPromotionConflictError("This payment offer is no longer active.")

        if offer.status == WaitlistPromotionOfferStatus.PAID:
            raise WaitlistPromotionConflictError("This payment offer has already been paid.")

        if offer.payment is not None:
            if offer.payment.status == PaymentStatus.SUCCESSFUL:
                offer.status = WaitlistPromotionOfferStatus.PAID
                await self.session.flush()
                raise WaitlistPromotionConflictError("This payment offer has already been paid.")
            if offer.payment.status == PaymentStatus.FAILED:
                raise WaitlistPromotionConflictError("This payment offer is no longer active.")
            if offer.gateway_checkout_url is None:
                raise WaitlistPromotionConflictError(
                    "This payment offer cannot be used right now because no checkout URL is available."
                )
            offer.status = WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED
            await self.session.flush()
            return WaitlistPromotionInitializationResult(checkout_url=offer.gateway_checkout_url)

        payment_result = await self.payment_service.initialize_registration_payment(
            registration=offer.registration,
            event=offer.registration.event,
        )
        if offer.registration.payment is None:
            raise WaitlistPromotionConflictError("Payment initialization did not attach a payment record.")

        offer.payment = offer.registration.payment
        offer.gateway_checkout_url = payment_result.checkout_url
        offer.status = WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED
        await self.session.flush()
        return WaitlistPromotionInitializationResult(checkout_url=payment_result.checkout_url)

    async def expire_stale_promotion_offers(self) -> list[WaitlistPromotionExpiryResult]:
        offers = await self.waitlist_promotion_repository.list_expired_active_offers(utc_now())
        results: list[WaitlistPromotionExpiryResult] = []
        for offer in offers:
            changed = await self._expire_offer(offer)
            if changed:
                results.append(
                    WaitlistPromotionExpiryResult(
                        public_token=offer.public_token,
                        reg_id=offer.registration.reg_id,
                        status=offer.status,
                    )
                )
        return results

    def build_payment_action_url(self, public_token: str) -> str:
        return (
            f"{self.settings.application_base_url.rstrip('/')}"
            f"/registrations/payment-offers/{public_token}/initialize"
        )

    async def _expire_offer(self, offer: WaitlistPromotionOffer) -> bool:
        if offer.status not in ACTIVE_WAITLIST_PROMOTION_STATUSES:
            return False

        offer.status = WaitlistPromotionOfferStatus.EXPIRED
        if offer.registration.state == RegistrationState.PENDING_PAYMENT:
            offer.registration.state = RegistrationState.FAILED
        if offer.payment is not None and offer.payment.status == PaymentStatus.PENDING:
            offer.payment.status = PaymentStatus.FAILED
            offer.payment.paid_at = None
        await self.session.flush()
        return True

    async def _load_actor(self, staff_id: str) -> StaffAccount:
        account = await self.staff_repository.get_by_id_with_access(staff_id)
        if account is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        return account

    def _resolve_offer_expiry(
        self,
        *,
        account: StaffAccount,
        requested_expiry: datetime | None,
    ) -> datetime:
        now = utc_now()
        if requested_expiry is not None:
            if account.role != StaffRole.ADMIN:
                raise StaffOperationForbiddenError("Only admin users can set a custom offer expiry.")
            if requested_expiry <= now:
                raise WaitlistPromotionValidationError("offer_expires_at must be in the future.")
            return requested_expiry

        return now + timedelta(minutes=self.settings.waitlist_promotion_default_expiry_minutes)

    async def _resequence_waitlist(self, event_id: str) -> None:
        waitlisted_registrations = await self.registration_repository.list_registrations_for_event(
            event_id,
            states=[RegistrationState.WAITLISTED],
            for_update=True,
        )
        for index, registration in enumerate(waitlisted_registrations, start=1):
            registration.waitlist_position = index
        await self.session.flush()

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

    def _build_user_notification_body(
        self,
        *,
        event_title: str,
        payment_action_url: str,
        offer_expires_at: datetime,
    ) -> str:
        formatted_expiry = offer_expires_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
        return (
            f"A spot has opened for {event_title}. Complete payment before {formatted_expiry} "
            f"using this secure payment link: {payment_action_url}"
        )
