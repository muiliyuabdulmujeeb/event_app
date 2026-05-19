from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import PaymentConfigurationError
from app.models.event import Event
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import BatchRegistration, Registration
from app.repositories.payment_repository import PaymentRepository
from app.services.payment_providers import (
    MockPaymentProvider,
    PaymentInitializationRequest,
    PaymentInitializationResult,
    PaymentProvider,
    PaystackPaymentProvider,
    SquadPaymentProvider,
)


@dataclass
class PaymentService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = PaymentRepository(self.session)

    async def initialize_registration_payment(
        self,
        *,
        registration: Registration,
        event: Event,
    ) -> PaymentInitializationResult:
        payment = await self.prepare_registration_payment(registration=registration, event=event)
        result = await self.initialize_existing_registration_payment(
            registration=registration,
            event=event,
            payment=payment,
        )
        return result

    async def prepare_registration_payment(
        self,
        *,
        registration: Registration,
        event: Event,
    ) -> Payment:
        attempt_number = await self.repository.get_next_registration_attempt_number(registration.id)
        gateway = self._resolve_gateway()
        payment = Payment(
            gateway=gateway,
            payment_reference=self._build_registration_reference(
                gateway,
                registration.reg_id,
                attempt_number=attempt_number,
            ),
            amount=event.price,
            status=PaymentStatus.PENDING,
            attempt_number=attempt_number,
            registration_id=registration.id,
        )
        await self.repository.create_payment(payment)
        registration.current_payment_id = payment.id
        await self.session.flush()
        await self.session.refresh(registration, attribute_names=["payment"])
        return payment

    async def initialize_existing_registration_payment(
        self,
        *,
        registration: Registration,
        event: Event,
        payment: Payment,
    ) -> PaymentInitializationResult:
        if payment.gateway_checkout_url:
            return PaymentInitializationResult(
                gateway=payment.gateway,
                payment_reference=payment.payment_reference,
                checkout_url=payment.gateway_checkout_url,
            )
        provider = self._build_provider(payment.gateway)
        payload = self._build_registration_initialization_request(
            registration=registration,
            event=event,
            reference=payment.payment_reference,
        )
        result = await provider.initialize_payment(payload)
        payment.gateway_checkout_url = result.checkout_url
        await self.session.flush()
        return result

    async def initialize_registration_payment_by_registration(
        self,
        *,
        registration: Registration,
        event: Event,
    ) -> PaymentInitializationResult:
        payment = registration.payment
        if payment is None or payment.status != PaymentStatus.PENDING:
            payment = await self.prepare_registration_payment(registration=registration, event=event)
        return await self.initialize_existing_registration_payment(
            registration=registration,
            event=event,
            payment=payment,
        )

    async def initialize_batch_payment(
        self,
        *,
        batch_registration: BatchRegistration,
    ) -> PaymentInitializationResult:
        gateway = self._resolve_gateway()
        provider = self._build_provider(gateway)
        payload = PaymentInitializationRequest(
            email=batch_registration.submitter_email,
            amount=batch_registration.total_amount,
            currency="NGN",
            reference=self._build_batch_reference(gateway, batch_registration.id),
            customer_name=batch_registration.submitter_name,
            callback_url=self._payment_callback_url(),
            metadata={
                "batch_id": batch_registration.id,
                "event_id": batch_registration.event_id,
                "submitter_email": batch_registration.submitter_email,
            },
        )
        result = await provider.initialize_payment(payload)

        batch_registration.payment_reference = result.payment_reference
        payment = Payment(
            gateway=result.gateway,
            payment_reference=result.payment_reference,
            amount=batch_registration.total_amount,
            status=PaymentStatus.PENDING,
            attempt_number=1,
            batch_registration=batch_registration,
            gateway_checkout_url=result.checkout_url,
        )
        await self.repository.create_payment(payment)
        return result

    def _resolve_gateway(self) -> PaymentGateway:
        try:
            return PaymentGateway(self.settings.active_payment_gateway.lower())
        except ValueError as exc:
            raise PaymentConfigurationError("ACTIVE_PAYMENT_GATEWAY is not supported.") from exc

    def _build_provider(self, gateway: PaymentGateway) -> PaymentProvider:
        if gateway == PaymentGateway.MOCK:
            return MockPaymentProvider(self.settings)
        if gateway == PaymentGateway.PAYSTACK:
            return PaystackPaymentProvider(self.settings)
        if gateway == PaymentGateway.SQUAD:
            return SquadPaymentProvider(self.settings)
        raise PaymentConfigurationError("ACTIVE_PAYMENT_GATEWAY is not supported.")

    def _build_registration_reference(
        self,
        gateway: PaymentGateway,
        reg_id: str,
        *,
        attempt_number: int,
    ) -> str:
        compact_reg_id = reg_id.replace("-", "")
        attempt_suffix = "" if attempt_number == 1 else f"-A{attempt_number}"
        if gateway == PaymentGateway.MOCK:
            return f"MOCK_{compact_reg_id}{attempt_suffix.replace('-', '_')}"
        if gateway == PaymentGateway.PAYSTACK:
            return f"PAYSTACK-{compact_reg_id}{attempt_suffix}"
        return f"SQUAD-{compact_reg_id}{attempt_suffix}"

    def _build_batch_reference(self, gateway: PaymentGateway, batch_id: str) -> str:
        compact_batch_id = batch_id.replace("-", "")
        if gateway == PaymentGateway.MOCK:
            return f"MOCK_{compact_batch_id}"
        if gateway == PaymentGateway.PAYSTACK:
            return f"PAYSTACK-{compact_batch_id}"
        return f"SQUAD-{compact_batch_id}"

    def _payment_callback_url(self) -> str | None:
        callback_url = self.settings.payment_callback_url.strip()
        return callback_url or None

    def _build_registration_initialization_request(
        self,
        *,
        registration: Registration,
        event: Event,
        reference: str,
    ) -> PaymentInitializationRequest:
        return PaymentInitializationRequest(
            email=registration.email,
            amount=event.price,
            currency="NGN",
            reference=reference,
            customer_name=f"{registration.first_name} {registration.last_name}".strip(),
            callback_url=self._payment_callback_url(),
            metadata={
                "registration_id": registration.id,
                "event_id": event.id,
                "reg_id": registration.reg_id,
            },
        )
