from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.payment import Payment, PaymentStatus
from app.models.registration import BatchRegistration, Registration, RegistrationState
from app.models.staff import StaffAccount
from app.services.payment_processing_service import (
    PAYMENT_FAILED_EVENT,
    PAYMENT_SUCCESS_EVENT,
    PaymentProcessingService,
)
from app.workers.payment_tasks import _expire_stale_payments, _process_payment_webhook


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
        "PAYSTACK_SECRET_KEY": "sk_test_paystack",
        "SQUAD_SECRET_KEY": "sandbox_sk_squad",
    }
    defaults.update(overrides)
    return Settings(**defaults)


async def create_event(
    db_session,
    *,
    created_by: StaffAccount,
    title: str,
    prefix: str,
    price: int,
    capacity: int | None,
    overflow_rule: OverflowRule,
    state: EventState = EventState.PUBLISHED,
    custom_fields: list[EventFieldDefinition] | None = None,
) -> Event:
    event = Event(
        title=title,
        description=f"{title} description",
        event_date=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix=prefix,
        price=price,
        capacity=capacity,
        overflow_rule=overflow_rule,
        state=state,
        created_by=created_by.id,
    )
    event.field_definitions = custom_fields or []
    db_session.add(event)
    await db_session.commit()
    result = await db_session.execute(
        select(Event)
        .where(Event.id == event.id)
        .options(selectinload(Event.field_definitions))
    )
    return result.scalar_one()


async def create_paid_single_registration(client, db_session, event: Event) -> tuple[dict, Payment]:
    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Chidi",
            "last_name": "Okonkwo",
            "email": "chidi@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )
    assert response.status_code == 201
    payment = (await db_session.execute(select(Payment))).scalar_one()
    return response.json(), payment


def build_batch_payload() -> dict:
    return {
        "submitter_name": "Chidi Okonkwo",
        "submitter_email": "submitter@example.com",
        "acknowledge_duplicates": False,
        "participants": [
            {
                "first_name": "Ngozi",
                "last_name": "Eze",
                "email": "ngozi@example.com",
                "custom_field_values": [],
            },
            {
                "first_name": "Emeka",
                "last_name": "Obi",
                "email": "emeka@example.com",
                "custom_field_values": [],
            },
            {
                "first_name": "Fatima",
                "last_name": "Aliyu",
                "email": "fatima@example.com",
                "custom_field_values": [],
            },
            {
                "first_name": "Chinedu",
                "last_name": "Nwosu",
                "email": "chinedu@example.com",
                "custom_field_values": [],
            },
        ],
    }


def paystack_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()


def squad_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest().upper()


@pytest.mark.asyncio
async def test_mock_confirm_transitions_single_registration_to_confirmed(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Paid Confirm Event",
        prefix="PCN",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    _, payment = await create_paid_single_registration(client, db_session, event)

    response = await client.post(f"/mock-payment/confirm/{payment.payment_reference}")

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}

    await db_session.rollback()
    db_session.expire_all()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert payment.paid_at is not None
    assert registration.state == RegistrationState.CONFIRMED


@pytest.mark.asyncio
async def test_mock_fail_transitions_single_registration_to_failed_and_releases_slot(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Paid Limited Event",
        prefix="PLT",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    event_id = event.id
    _, payment = await create_paid_single_registration(client, db_session, event)

    fail_response = await client.post(f"/mock-payment/fail/{payment.payment_reference}")
    assert fail_response.status_code == 200

    await db_session.rollback()
    db_session.expire_all()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    failed_registration = (await db_session.execute(select(Registration))).scalar_one()
    assert payment.status == PaymentStatus.FAILED
    assert failed_registration.state == RegistrationState.FAILED

    retry_response = await client.post(
        f"/register/{event_id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )
    assert retry_response.status_code == 201
    assert retry_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_mock_confirm_transitions_paid_batch_to_confirmed(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Batch Confirm Event",
        prefix="BCN",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )

    response = await client.post(f"/register/{event.id}/batch", json=build_batch_payload())
    assert response.status_code == 201
    payment = (await db_session.execute(select(Payment))).scalar_one()

    confirm_response = await client.post(f"/mock-payment/confirm/{payment.payment_reference}")
    assert confirm_response.status_code == 200

    await db_session.rollback()
    db_session.expire_all()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    registrations = (await db_session.execute(select(Registration).order_by(Registration.email))).scalars().all()
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert payment.paid_at is not None
    assert len(registrations) == 4
    assert all(registration.state == RegistrationState.CONFIRMED for registration in registrations)


@pytest.mark.asyncio
async def test_mock_fail_transitions_paid_batch_to_failed_and_releases_capacity(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Batch Fail Event",
        prefix="BFL",
        price=5000,
        capacity=4,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    event_id = event.id

    response = await client.post(f"/register/{event.id}/batch", json=build_batch_payload())
    assert response.status_code == 201
    payment = (await db_session.execute(select(Payment))).scalar_one()

    fail_response = await client.post(f"/mock-payment/fail/{payment.payment_reference}")
    assert fail_response.status_code == 200

    await db_session.rollback()
    db_session.expire_all()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert payment.status == PaymentStatus.FAILED
    assert all(registration.state == RegistrationState.FAILED for registration in registrations)

    retry_response = await client.post(
        f"/register/{event_id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )
    assert retry_response.status_code == 201
    assert retry_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_paystack_webhook_with_valid_signature_enqueues_processing(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(PAYSTACK_SECRET_KEY="sk_test_webhook")
    override_app_settings(settings)
    payload = {
        "event": "charge.success",
        "data": {
            "reference": "PAYSTACK-TEC2026ABC123",
            "paidAt": "2026-05-14T10:00:00Z",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/paystack",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-paystack-signature": paystack_signature(raw_body, "sk_test_webhook"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert captured_payment_tasks == [
        {
            "event_type": PAYMENT_SUCCESS_EVENT,
            "reference": "PAYSTACK-TEC2026ABC123",
            "paid_at": "2026-05-14T10:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_paystack_webhook_with_invalid_signature_returns_400(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(PAYSTACK_SECRET_KEY="sk_test_webhook")
    override_app_settings(settings)
    payload = {
        "event": "charge.success",
        "data": {"reference": "PAYSTACK-TEC2026ABC123"},
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/paystack",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-paystack-signature": "invalid",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Webhook signature is invalid."}
    assert captured_payment_tasks == []


@pytest.mark.asyncio
async def test_paystack_charge_dispute_event_is_ignored_safely(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(PAYSTACK_SECRET_KEY="sk_test_webhook")
    override_app_settings(settings)
    payload = {
        "event": "charge.dispute",
        "data": {"reference": "PAYSTACK-TEC2026ABC123"},
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/paystack",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-paystack-signature": paystack_signature(raw_body, "sk_test_webhook"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert captured_payment_tasks == []


@pytest.mark.asyncio
async def test_squad_webhook_with_valid_signature_enqueues_processing(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(SQUAD_SECRET_KEY="sandbox_sk_webhook")
    override_app_settings(settings)
    payload = {
        "Event": "charge_successful",
        "TransactionRef": "SQTEST6389164239897900003",
        "Body": {
            "transaction_ref": "SQTEST6389164239897900003",
            "transaction_status": "Success",
            "created_at": "2026-05-14T12:00:00Z",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/squad",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-squad-encrypted-body": squad_signature(raw_body, "sandbox_sk_webhook"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert captured_payment_tasks == [
        {
            "event_type": PAYMENT_SUCCESS_EVENT,
            "reference": "SQTEST6389164239897900003",
            "paid_at": "2026-05-14T12:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_squad_webhook_with_invalid_signature_returns_400(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(SQUAD_SECRET_KEY="sandbox_sk_webhook")
    override_app_settings(settings)
    payload = {
        "Event": "charge_successful",
        "TransactionRef": "SQTEST6389164239897900003",
        "Body": {
            "transaction_ref": "SQTEST6389164239897900003",
            "transaction_status": "Success",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/squad",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-squad-encrypted-body": "INVALID",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Webhook signature is invalid."}
    assert captured_payment_tasks == []


@pytest.mark.asyncio
async def test_squad_unsupported_event_is_ignored_safely(
    client,
    override_app_settings,
    captured_payment_tasks: list[dict],
) -> None:
    settings = build_settings(SQUAD_SECRET_KEY="sandbox_sk_webhook")
    override_app_settings(settings)
    payload = {
        "Event": "charge_reversed",
        "TransactionRef": "SQTEST6389164239897900003",
        "Body": {
            "transaction_ref": "SQTEST6389164239897900003",
            "transaction_status": "Failed",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/payments/webhook/squad",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-squad-encrypted-body": squad_signature(raw_body, "sandbox_sk_webhook"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert captured_payment_tasks == []


@pytest.mark.asyncio
async def test_mock_payment_endpoints_return_404_for_unknown_reference(
    client,
) -> None:
    confirm_response = await client.post("/mock-payment/confirm/UNKNOWN_REF")
    fail_response = await client.post("/mock-payment/fail/UNKNOWN_REF")

    assert confirm_response.status_code == 404
    assert confirm_response.json() == {"detail": "Payment with reference 'UNKNOWN_REF' was not found."}
    assert fail_response.status_code == 404
    assert fail_response.json() == {"detail": "Payment with reference 'UNKNOWN_REF' was not found."}


@pytest.mark.asyncio
async def test_payment_processing_service_is_idempotent_for_duplicate_success_webhooks(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Idempotent Event",
        prefix="IDM",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    _, payment = await create_paid_single_registration(client, db_session, event)

    service = PaymentProcessingService(session=db_session, settings=build_settings())
    paid_at = datetime(2026, 5, 14, 13, 0, tzinfo=timezone.utc)

    first = await service.process_event(
        event_type=PAYMENT_SUCCESS_EVENT,
        reference=payment.payment_reference,
        paid_at=paid_at,
    )
    second = await service.process_event(
        event_type=PAYMENT_SUCCESS_EVENT,
        reference=payment.payment_reference,
        paid_at=paid_at,
    )
    await db_session.commit()

    payment = (await db_session.execute(select(Payment))).scalar_one()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    assert first.processed is True
    assert second.processed is False
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert payment.paid_at == paid_at
    assert registration.state == RegistrationState.CONFIRMED


@pytest.mark.asyncio
async def test_payment_processing_service_is_idempotent_for_duplicate_failed_webhooks(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Duplicate Fail Event",
        prefix="DFA",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    _, payment = await create_paid_single_registration(client, db_session, event)

    service = PaymentProcessingService(session=db_session, settings=build_settings())

    first = await service.process_event(
        event_type=PAYMENT_FAILED_EVENT,
        reference=payment.payment_reference,
    )
    second = await service.process_event(
        event_type=PAYMENT_FAILED_EVENT,
        reference=payment.payment_reference,
    )
    await db_session.commit()

    payment = (await db_session.execute(select(Payment))).scalar_one()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    assert first.processed is True
    assert second.processed is False
    assert payment.status == PaymentStatus.FAILED
    assert payment.paid_at is None
    assert registration.state == RegistrationState.FAILED


@pytest.mark.asyncio
async def test_payment_processing_service_does_not_revive_failed_payment_on_late_success(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Late Success Event",
        prefix="LTS",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    _, payment = await create_paid_single_registration(client, db_session, event)

    service = PaymentProcessingService(session=db_session, settings=build_settings())
    failed = await service.process_event(
        event_type=PAYMENT_FAILED_EVENT,
        reference=payment.payment_reference,
    )
    late_success = await service.process_event(
        event_type=PAYMENT_SUCCESS_EVENT,
        reference=payment.payment_reference,
        paid_at=datetime(2026, 5, 14, 15, 0, tzinfo=timezone.utc),
    )
    await db_session.commit()

    payment = (await db_session.execute(select(Payment))).scalar_one()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    assert failed.processed is True
    assert late_success.processed is False
    assert payment.status == PaymentStatus.FAILED
    assert payment.paid_at is None
    assert registration.state == RegistrationState.FAILED


@pytest.mark.asyncio
async def test_process_payment_webhook_task_confirms_batch_end_to_end(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Task Batch Event",
        prefix="TSK",
        price=5000,
        capacity=4,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    response = await client.post(f"/register/{event.id}/batch", json=build_batch_payload())
    assert response.status_code == 201

    payment = (await db_session.execute(select(Payment))).scalar_one()
    result = await _process_payment_webhook(
        {
            "event_type": PAYMENT_SUCCESS_EVENT,
            "reference": payment.payment_reference,
            "paid_at": "2026-05-14T14:00:00Z",
        }
    )

    await db_session.rollback()
    db_session.expire_all()
    registrations = (await db_session.execute(select(Registration))).scalars().all()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert result["processed"] is True
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert len(registrations) == 4
    assert all(registration.state == RegistrationState.CONFIRMED for registration in registrations)


@pytest.mark.asyncio
async def test_expire_stale_payments_marks_pending_single_and_batch_failed(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    single_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Expire Single Event",
        prefix="EXP",
        price=5000,
        capacity=2,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    _, single_payment = await create_paid_single_registration(client, db_session, single_event)

    batch_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Expire Batch Event",
        prefix="EXB",
        price=5000,
        capacity=4,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    batch_response = await client.post(f"/register/{batch_event.id}/batch", json=build_batch_payload())
    assert batch_response.status_code == 201
    payments = (await db_session.execute(select(Payment).order_by(Payment.created_at))).scalars().all()
    batch_payment = next(payment for payment in payments if payment.id != single_payment.id)

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=31)
    single_registration = (await db_session.execute(select(Registration).where(Registration.id == single_payment.registration_id))).scalar_one()
    single_registration.registered_at = stale_time
    single_payment.created_at = stale_time

    batch_registration = (await db_session.execute(select(BatchRegistration).where(BatchRegistration.id == batch_payment.batch_id))).scalar_one()
    batch_registration.created_at = stale_time
    batch_payment.created_at = stale_time
    await db_session.commit()

    results = await _expire_stale_payments()

    await db_session.rollback()
    db_session.expire_all()
    payments = (await db_session.execute(select(Payment).order_by(Payment.payment_reference))).scalars().all()
    registrations = (await db_session.execute(select(Registration).order_by(Registration.email))).scalars().all()
    assert len(results) == 2
    assert all(payment.status == PaymentStatus.FAILED for payment in payments)
    assert all(registration.state == RegistrationState.FAILED for registration in registrations)
