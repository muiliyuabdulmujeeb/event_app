from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import BatchRegistration, Registration, RegistrationState
from app.services.payment_providers import (
    MockPaymentProvider,
    PaymentInitializationRequest,
    PaymentInitializationResult,
    PaystackPaymentProvider,
    SquadPaymentProvider,
)
from app.services.payment_service import PaymentService


def build_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb",
        "TEST_DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb_test",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "changeme",
        "EMAIL_PROVIDER": "mock",
        "ACTIVE_PAYMENT_GATEWAY": "mock",
        "MOCK_PAYMENT_BASE_URL": "http://localhost:8000",
        "PAYSTACK_API_BASE_URL": "https://api.paystack.co",
        "SQUAD_API_BASE_URL": "https://sandbox-api-d.squadco.com",
        "PAYMENT_CALLBACK_URL": "https://frontend.local/payment/success",
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_mock_payment_provider_returns_fake_checkout_url() -> None:
    provider = MockPaymentProvider(build_settings())

    result = await provider.initialize_payment(
        PaymentInitializationRequest(
            email="chidi@example.com",
            amount=5000,
            currency="NGN",
            reference="MOCK_TEC2026ABC123",
            customer_name="Chidi Okonkwo",
            callback_url=None,
            metadata={},
        )
    )

    assert result == PaymentInitializationResult(
        gateway=PaymentGateway.MOCK,
        payment_reference="MOCK_TEC2026ABC123",
        checkout_url="http://localhost:8000/mock-payment/pay?ref=MOCK_TEC2026ABC123",
    )


@pytest.mark.asyncio
async def test_paystack_provider_uses_initialize_transaction_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": "https://checkout.paystack.com/3ni8kdavz62431k",
                    "access_code": "3ni8kdavz62431k",
                    "reference": "PAYSTACK-TEC2026ABC123",
                },
            },
        )

    settings = build_settings(
        ACTIVE_PAYMENT_GATEWAY="paystack",
        PAYSTACK_SECRET_KEY="sk_test_paystack",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = PaystackPaymentProvider(settings, client=client)
        result = await provider.initialize_payment(
            PaymentInitializationRequest(
                email="chidi@example.com",
                amount=5000,
                currency="NGN",
                reference="PAYSTACK-TEC2026ABC123",
                customer_name="Chidi Okonkwo",
                callback_url="https://frontend.local/payment/success",
                metadata={"registration_id": "rdb_123", "reg_id": "TEC-2026-ABC123"},
            )
        )

    assert captured["url"] == "https://api.paystack.co/transaction/initialize"
    assert captured["authorization"] == "Bearer sk_test_paystack"
    assert captured["body"] == {
        "email": "chidi@example.com",
        "amount": "5000",
        "reference": "PAYSTACK-TEC2026ABC123",
        "callback_url": "https://frontend.local/payment/success",
        "metadata": json.dumps({"registration_id": "rdb_123", "reg_id": "TEC-2026-ABC123"}),
    }
    assert result == PaymentInitializationResult(
        gateway=PaymentGateway.PAYSTACK,
        payment_reference="PAYSTACK-TEC2026ABC123",
        checkout_url="https://checkout.paystack.com/3ni8kdavz62431k",
    )


@pytest.mark.asyncio
async def test_squad_provider_uses_initiate_payment_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "status": 200,
                "message": "success",
                "data": {
                    "transaction_ref": "SQUAD-bat123456",
                    "checkout_url": "https://sandbox-pay.squadco.com/SQUAD-bat123456",
                },
            },
        )

    settings = build_settings(
        ACTIVE_PAYMENT_GATEWAY="squad",
        SQUAD_SECRET_KEY="sandbox_sk_squad",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SquadPaymentProvider(settings, client=client)
        result = await provider.initialize_payment(
            PaymentInitializationRequest(
                email="submitter@example.com",
                amount=20000,
                currency="NGN",
                reference="SQUAD-bat123456",
                customer_name="Chidi Okonkwo",
                callback_url="https://frontend.local/payment/success",
                metadata={"batch_id": "bat123456", "event_id": "evt_123"},
            )
        )

    assert captured["url"] == "https://sandbox-api-d.squadco.com/transaction/initiate"
    assert captured["authorization"] == "Bearer sandbox_sk_squad"
    assert captured["body"] == {
        "email": "submitter@example.com",
        "amount": 20000,
        "currency": "NGN",
        "initiate_type": "inline",
        "transaction_ref": "SQUAD-bat123456",
        "customer_name": "Chidi Okonkwo",
        "callback_url": "https://frontend.local/payment/success",
        "payment_channels": ["card", "bank", "ussd", "transfer"],
        "metadata": {"batch_id": "bat123456", "event_id": "evt_123"},
    }
    assert result == PaymentInitializationResult(
        gateway=PaymentGateway.SQUAD,
        payment_reference="SQUAD-bat123456",
        checkout_url="https://sandbox-pay.squadco.com/SQUAD-bat123456",
    )


@pytest.mark.asyncio
async def test_payment_service_creates_single_payment_record_with_configured_provider(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    seeded_paid_published_event,
) -> None:
    registration = Registration(
        event_id=seeded_paid_published_event.id,
        first_name="Chidi",
        last_name="Okonkwo",
        email="chidi@example.com",
        reg_id="TEC-2026-ABC123",
        state=RegistrationState.PENDING_PAYMENT,
    )
    db_session.add(registration)
    await db_session.flush()

    service = PaymentService(
        session=db_session,
        settings=build_settings(ACTIVE_PAYMENT_GATEWAY="paystack"),
    )
    captured: dict[str, object] = {}

    class StubProvider:
        gateway = PaymentGateway.PAYSTACK

        async def initialize_payment(
            self,
            payload: PaymentInitializationRequest,
        ) -> PaymentInitializationResult:
            captured["payload"] = payload
            return PaymentInitializationResult(
                gateway=PaymentGateway.PAYSTACK,
                payment_reference="PAYSTACK-TEC2026ABC123",
                checkout_url="https://checkout.paystack.com/paystack-token",
            )

    monkeypatch.setattr(service, "_build_provider", lambda gateway: StubProvider())

    result = await service.initialize_registration_payment(
        registration=registration,
        event=seeded_paid_published_event,
    )

    assert result.checkout_url == "https://checkout.paystack.com/paystack-token"
    assert captured["payload"] == PaymentInitializationRequest(
        email="chidi@example.com",
        amount=5000,
        currency="NGN",
        reference="PAYSTACK-TEC2026ABC123",
        customer_name="Chidi Okonkwo",
        callback_url="https://frontend.local/payment/success",
        metadata={
            "registration_id": registration.id,
            "event_id": seeded_paid_published_event.id,
            "reg_id": "TEC-2026-ABC123",
        },
    )

    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert payment.gateway == PaymentGateway.PAYSTACK
    assert payment.payment_reference == "PAYSTACK-TEC2026ABC123"
    assert payment.status == PaymentStatus.PENDING
    assert payment.registration_id == registration.id


@pytest.mark.asyncio
async def test_payment_service_creates_batch_payment_record_with_configured_provider(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    seeded_paid_published_event,
) -> None:
    batch_registration = BatchRegistration(
        event_id=seeded_paid_published_event.id,
        submitter_name="Batch Submitter",
        submitter_email="submitter@example.com",
        total_amount=20000,
        payment_reference=None,
    )
    db_session.add(batch_registration)
    await db_session.flush()

    service = PaymentService(
        session=db_session,
        settings=build_settings(ACTIVE_PAYMENT_GATEWAY="squad"),
    )
    captured: dict[str, object] = {}

    class StubProvider:
        gateway = PaymentGateway.SQUAD

        async def initialize_payment(
            self,
            payload: PaymentInitializationRequest,
        ) -> PaymentInitializationResult:
            captured["payload"] = payload
            return PaymentInitializationResult(
                gateway=PaymentGateway.SQUAD,
                payment_reference="SQUAD-bat123456",
                checkout_url="https://sandbox-pay.squadco.com/SQUAD-bat123456",
            )

    monkeypatch.setattr(service, "_build_provider", lambda gateway: StubProvider())

    result = await service.initialize_batch_payment(batch_registration=batch_registration)

    assert result.checkout_url == "https://sandbox-pay.squadco.com/SQUAD-bat123456"
    assert captured["payload"] == PaymentInitializationRequest(
        email="submitter@example.com",
        amount=20000,
        currency="NGN",
        reference=f"SQUAD-{batch_registration.id.replace('-', '')}",
        customer_name="Batch Submitter",
        callback_url="https://frontend.local/payment/success",
        metadata={
            "batch_id": batch_registration.id,
            "event_id": seeded_paid_published_event.id,
            "submitter_email": "submitter@example.com",
        },
    )
    assert batch_registration.payment_reference == "SQUAD-bat123456"

    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert payment.gateway == PaymentGateway.SQUAD
    assert payment.payment_reference == "SQUAD-bat123456"
    assert payment.status == PaymentStatus.PENDING
    assert payment.batch_id == batch_registration.id
