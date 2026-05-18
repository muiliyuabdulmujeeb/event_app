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
        gateway = self._resolve_gateway()
        provider = self._build_provider(gateway)
        payload = PaymentInitializationRequest(
            email=registration.email,
            amount=event.price,
            currency="NGN",
            reference=self._build_registration_reference(gateway, registration.reg_id),
            customer_name=f"{registration.first_name} {registration.last_name}".strip(),
            callback_url=self._payment_callback_url(),
            metadata={
                "registration_id": registration.id,
                "event_id": event.id,
                "reg_id": registration.reg_id,
            },
        )
        result = await provider.initialize_payment(payload)

        payment = Payment(
            gateway=result.gateway,
            payment_reference=result.payment_reference,
            amount=event.price,
            status=PaymentStatus.PENDING,
            registration=registration,
        )
        await self.repository.create_payment(payment)
        return result

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
            batch_registration=batch_registration,
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

    def _build_registration_reference(self, gateway: PaymentGateway, reg_id: str) -> str:
        compact_reg_id = reg_id.replace("-", "")
        if gateway == PaymentGateway.MOCK:
            return f"MOCK_{compact_reg_id}"
        if gateway == PaymentGateway.PAYSTACK:
            return f"PAYSTACK-{compact_reg_id}"
        return f"SQUAD-{compact_reg_id}"

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
