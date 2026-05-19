from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    DuplicateRegistrationError,
    EventConflictError,
    EventNotFoundError,
    ExceptionRegistrationOfferConflictError,
    ExceptionRegistrationOfferExpiredError,
    ExceptionRegistrationOfferForbiddenError,
    ExceptionRegistrationOfferNotFoundError,
    ExceptionRegistrationOfferValidationError,
)
from app.core.security import utc_now
from app.models.event import Event, EventState
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.exception_registration_offer_audit import (
    ExceptionRegistrationOfferAudit,
    ExceptionRegistrationOfferAuditAction,
    ExceptionRegistrationOfferAuditActorType,
)
from app.models.payment import PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccount, StaffRole
from app.repositories.event_repository import EventRepository
from app.repositories.exception_registration_repository import (
    ExceptionOfferListFilters,
    ExceptionRegistrationRepository,
)
from app.repositories.registration_repository import RegistrationRepository
from app.schemas.email import EmailMessage
from app.schemas.exception_registration import (
    ExceptionOfferRegistrationRequest,
    ExceptionOfferRegistrationResponse,
    ExceptionRegistrationOfferAuditEntryResponse,
    ExceptionRegistrationOfferAuditListResponse,
    ExceptionRegistrationOfferCreateRequest,
    ExceptionRegistrationOfferListResponse,
    ExceptionRegistrationOfferResponse,
    ExceptionRegistrationOfferRevokeResponse,
)
from app.services.email_templates import build_ticket_email_message
from app.services.event_authorization_service import EventAuthorizationService
from app.services.payment_service import PaymentService
from app.services.registration_service import RegistrationService


@dataclass(frozen=True)
class ExceptionRegistrationServiceResult:
    response: ExceptionOfferRegistrationResponse
    ticket_email_message: EmailMessage | None = None


@dataclass(frozen=True)
class ExceptionOfferPaymentInitializationResult:
    checkout_url: str


@dataclass
class ExceptionRegistrationService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.event_repository = EventRepository(self.session)
        self.exception_repository = ExceptionRegistrationRepository(self.session)
        self.registration_repository = RegistrationRepository(self.session)
        self.registration_service = RegistrationService(self.session, self.settings)
        self.payment_service = PaymentService(self.session, self.settings)
        self.authorization_service = EventAuthorizationService(self.session)

    async def create_offer(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        payload: ExceptionRegistrationOfferCreateRequest,
    ) -> ExceptionRegistrationOfferResponse:
        event = await self._require_offer_manager(actor=actor, event_id=event_id)
        if event.is_free and payload.payment_waived:
            raise ExceptionRegistrationOfferValidationError(
                "payment_waived can only be used for paid events."
            )
        if payload.expires_at <= utc_now():
            raise ExceptionRegistrationOfferValidationError("expires_at must be in the future.")

        offer = ExceptionRegistrationOffer(
            event_id=event.id,
            issued_by_staff_id=actor.id,
            target_email=payload.target_email.lower(),
            target_first_name=payload.target_first_name,
            target_last_name=payload.target_last_name,
            source_reg_id=payload.source_reg_id,
            payment_waived=payload.payment_waived,
            capacity_override=True,
            expires_at=payload.expires_at,
        )
        await self.exception_repository.create_offer(offer)
        await self._append_audit(
            offer=offer,
            action=ExceptionRegistrationOfferAuditAction.ISSUED,
            actor_type=ExceptionRegistrationOfferAuditActorType.STAFF,
            actor_staff_id=actor.id,
            details=payload.note,
        )
        return self._build_offer_response(offer)

    async def list_offers(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        status: ExceptionRegistrationOfferStatus | None,
        target_email: str | None,
    ) -> ExceptionRegistrationOfferListResponse:
        await self._require_offer_manager(actor=actor, event_id=event_id)
        offers = await self.exception_repository.list_offers_for_event(
            event_id,
            filters=ExceptionOfferListFilters(
                status=status,
                target_email=target_email.strip().lower() if target_email is not None else None,
            ),
        )
        return ExceptionRegistrationOfferListResponse(
            event_id=event_id,
            offers=[self._build_offer_response(offer) for offer in offers],
            total=len(offers),
        )

    async def get_offer_audit(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        offer_id: str,
    ) -> ExceptionRegistrationOfferAuditListResponse:
        await self._require_offer_manager(actor=actor, event_id=event_id)
        offer = await self.exception_repository.get_offer_by_id(event_id=event_id, offer_id=offer_id)
        if offer is None:
            raise ExceptionRegistrationOfferNotFoundError()
        entries = await self.exception_repository.list_audit_entries(offer.id)
        return ExceptionRegistrationOfferAuditListResponse(
            offer_id=offer.id,
            entries=[
                ExceptionRegistrationOfferAuditEntryResponse(
                    action=entry.action,
                    actor_type=entry.actor_type,
                    actor_staff_id=entry.actor_staff_id,
                    details=entry.details,
                    created_at=entry.created_at,
                )
                for entry in entries
            ],
        )

    async def revoke_offer(
        self,
        *,
        actor: StaffAccount,
        event_id: str,
        offer_id: str,
        reason: str,
    ) -> ExceptionRegistrationOfferRevokeResponse:
        await self._require_offer_manager(actor=actor, event_id=event_id)
        offer = await self.exception_repository.get_offer_by_id(
            event_id=event_id,
            offer_id=offer_id,
            for_update=True,
        )
        if offer is None:
            raise ExceptionRegistrationOfferNotFoundError()
        if offer.status == ExceptionRegistrationOfferStatus.ISSUED and offer.expires_at <= utc_now():
            await self._expire_offer(offer, details="Offer expired before revocation.")
            raise ExceptionRegistrationOfferExpiredError(commit_changes=True)
        if offer.status != ExceptionRegistrationOfferStatus.ISSUED:
            raise ExceptionRegistrationOfferConflictError("This exception registration offer can no longer be revoked.")

        offer.status = ExceptionRegistrationOfferStatus.REVOKED
        await self._append_audit(
            offer=offer,
            action=ExceptionRegistrationOfferAuditAction.REVOKED,
            actor_type=ExceptionRegistrationOfferAuditActorType.STAFF,
            actor_staff_id=actor.id,
            details=reason,
        )
        return ExceptionRegistrationOfferRevokeResponse(
            id=offer.id,
            status=offer.status,
        )

    async def consume_offer(
        self,
        *,
        public_token: str,
        payload: ExceptionOfferRegistrationRequest,
    ) -> ExceptionRegistrationServiceResult:
        offer = await self.exception_repository.get_offer_by_public_token(public_token, for_update=True)
        if offer is None:
            raise ExceptionRegistrationOfferNotFoundError()
        if offer.status == ExceptionRegistrationOfferStatus.ISSUED and offer.expires_at <= utc_now():
            await self._expire_offer(offer, details="Offer expired before registration could be completed.")
            await self._append_rejection_audit(offer, "Attempted to register with an expired exception offer.")
            raise ExceptionRegistrationOfferExpiredError(commit_changes=True)
        if offer.status != ExceptionRegistrationOfferStatus.ISSUED:
            await self._append_rejection_audit(offer, "Attempted to reuse an inactive exception registration offer.")
            raise ExceptionRegistrationOfferConflictError(
                "This exception registration offer is no longer active.",
                commit_changes=True,
            )

        await self._append_audit(
            offer=offer,
            action=ExceptionRegistrationOfferAuditAction.REGISTRATION_ATTEMPTED,
            actor_type=ExceptionRegistrationOfferAuditActorType.PUBLIC,
            details=f"Attempted registration with email {payload.email.lower()}.",
        )

        if payload.email.lower() != offer.target_email:
            await self._append_rejection_audit(offer, "Submitted email does not match the targeted exception offer.")
            raise ExceptionRegistrationOfferConflictError(
                "This exception registration offer is not valid for the submitted email address.",
                commit_changes=True,
            )

        try:
            event = offer.event
            self.registration_service._ensure_event_accepts_registration(event)
            if event.capacity is not None:
                event = await self.registration_repository.lock_event(event.id)
                self.registration_service._ensure_event_accepts_registration(event)

            if await self.registration_repository.email_exists_for_event(event.id, payload.email):
                raise DuplicateRegistrationError()

            submitted_values = self.registration_service._normalize_custom_field_values(payload.custom_field_values)
            self.registration_service._validate_custom_field_values(event, submitted_values)

            registration_state = (
                RegistrationState.CONFIRMED
                if event.is_free or offer.payment_waived
                else RegistrationState.PENDING_PAYMENT
            )
            registration = Registration(
                event_id=event.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email.lower(),
                reg_id=await self.registration_service._generate_reg_id(event),
                state=registration_state,
            )
            registration.field_values = self.registration_service._build_field_values(submitted_values)
            await self.registration_repository.create_registration(registration)

            if registration_state == RegistrationState.PENDING_PAYMENT:
                await self.payment_service.prepare_registration_payment(registration=registration, event=event)

            offer.status = ExceptionRegistrationOfferStatus.USED
            offer.used_registration = registration
            await self.session.flush()
            await self._append_audit(
                offer=offer,
                action=ExceptionRegistrationOfferAuditAction.REGISTRATION_SUCCEEDED,
                actor_type=ExceptionRegistrationOfferAuditActorType.PUBLIC,
                details=f"Created registration {registration.reg_id}.",
            )
        except AppError as exc:
            await self._append_rejection_audit(offer, exc.detail)
            exc.commit_changes = True
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise EventConflictError(
                "The registration could not be saved because it conflicts with existing data."
            ) from exc

        payment_action_url = (
            self.build_payment_action_url(offer.public_token)
            if registration.state == RegistrationState.PENDING_PAYMENT
            else None
        )
        ticket_email_message = (
            build_ticket_email_message(self.settings, event=event, registration=registration)
            if registration.state == RegistrationState.CONFIRMED
            else None
        )
        message = (
            "Registration confirmed via exception offer."
            if registration.state == RegistrationState.CONFIRMED
            else "Registration created via exception offer. Complete payment to confirm your spot."
        )
        return ExceptionRegistrationServiceResult(
            response=ExceptionOfferRegistrationResponse(
                reg_id=registration.reg_id,
                state=registration.state,
                payment_waived=offer.payment_waived,
                payment_action_url=payment_action_url,
                message=message,
            ),
            ticket_email_message=ticket_email_message,
        )

    async def initialize_offer_payment(self, public_token: str) -> ExceptionOfferPaymentInitializationResult:
        offer = await self.exception_repository.get_offer_by_public_token(public_token, for_update=True)
        if offer is None:
            raise ExceptionRegistrationOfferNotFoundError()
        if offer.used_registration is None or offer.status != ExceptionRegistrationOfferStatus.USED:
            raise ExceptionRegistrationOfferConflictError("This exception registration offer is no longer active.")
        if offer.payment_waived or offer.used_registration.event.is_free:
            raise ExceptionRegistrationOfferConflictError("This exception registration does not require payment.")

        registration = offer.used_registration
        if registration.state != RegistrationState.PENDING_PAYMENT:
            if registration.state == RegistrationState.CONFIRMED:
                raise ExceptionRegistrationOfferConflictError("This exception registration has already been paid.")
            raise ExceptionRegistrationOfferConflictError("This payment link is no longer active.")

        if registration.payment is not None:
            if registration.payment.status == PaymentStatus.SUCCESSFUL:
                raise ExceptionRegistrationOfferConflictError("This exception registration has already been paid.")
            if registration.payment.status == PaymentStatus.FAILED:
                raise ExceptionRegistrationOfferConflictError("This payment link is no longer active.")
            if offer.gateway_checkout_url is not None:
                return ExceptionOfferPaymentInitializationResult(checkout_url=offer.gateway_checkout_url)

        if registration.payment is None:
            raise ExceptionRegistrationOfferConflictError(
                "This payment link cannot be used right now because no pending payment exists."
            )

        payment_result = await self.payment_service.initialize_existing_registration_payment(
            registration=registration,
            event=registration.event,
            payment=registration.payment,
        )
        offer.gateway_checkout_url = payment_result.checkout_url
        await self.session.flush()
        return ExceptionOfferPaymentInitializationResult(checkout_url=payment_result.checkout_url)

    def build_registration_action_url(self, public_token: str) -> str:
        return (
            f"{self.settings.application_base_url.rstrip('/')}"
            f"/registrations/exception-offers/{public_token}/register"
        )

    def build_payment_action_url(self, public_token: str) -> str:
        return (
            f"{self.settings.application_base_url.rstrip('/')}"
            f"/registrations/exception-offers/{public_token}/payments/initialize"
        )

    async def _require_offer_manager(self, *, actor: StaffAccount, event_id: str) -> Event:
        event = await self.event_repository.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError()
        if actor.role != StaffRole.ADMIN:
            raise ExceptionRegistrationOfferForbiddenError(
                "Only admin users can manage exception registration offers."
            )
        if event.created_by == actor.id:
            return event
        has_permission = await self.authorization_service.has_delegated_permission(
            actor_id=actor.id,
            event_id=event_id,
            permission_name="can_manage_exception_offers",
        )
        if not has_permission:
            raise ExceptionRegistrationOfferForbiddenError(
                "You do not have permission to manage exception registration offers for this event."
            )
        return event

    async def _append_rejection_audit(self, offer: ExceptionRegistrationOffer, details: str) -> None:
        await self._append_audit(
            offer=offer,
            action=ExceptionRegistrationOfferAuditAction.REGISTRATION_REJECTED,
            actor_type=ExceptionRegistrationOfferAuditActorType.PUBLIC,
            details=details,
        )

    async def _append_audit(
        self,
        *,
        offer: ExceptionRegistrationOffer,
        action: ExceptionRegistrationOfferAuditAction,
        actor_type: ExceptionRegistrationOfferAuditActorType,
        details: str | None = None,
        actor_staff_id: str | None = None,
    ) -> None:
        await self.exception_repository.create_audit_entry(
            ExceptionRegistrationOfferAudit(
                offer_id=offer.id,
                action=action,
                actor_type=actor_type,
                actor_staff_id=actor_staff_id,
                details=details,
            )
        )

    async def _expire_offer(self, offer: ExceptionRegistrationOffer, *, details: str) -> None:
        offer.status = ExceptionRegistrationOfferStatus.EXPIRED
        await self._append_audit(
            offer=offer,
            action=ExceptionRegistrationOfferAuditAction.EXPIRED,
            actor_type=ExceptionRegistrationOfferAuditActorType.SYSTEM,
            details=details,
        )

    def _build_offer_response(
        self,
        offer: ExceptionRegistrationOffer,
    ) -> ExceptionRegistrationOfferResponse:
        return ExceptionRegistrationOfferResponse(
            id=offer.id,
            event_id=offer.event_id,
            public_token=offer.public_token,
            registration_action_url=self.build_registration_action_url(offer.public_token),
            target_email=offer.target_email,
            payment_waived=offer.payment_waived,
            capacity_override=offer.capacity_override,
            status=offer.status,
            expires_at=offer.expires_at,
            created_at=offer.created_at,
        )
