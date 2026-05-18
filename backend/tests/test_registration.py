from __future__ import annotations

from datetime import datetime, timezone
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import RegistrationValidationError
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.payment import Payment, PaymentStatus
from app.models.registration import BatchRegistration, Registration, RegistrationState
from app.models.staff import StaffAccount
from app.services.registration_service import RegistrationService


REG_ID_PATTERN = re.compile(r"^[A-Z0-9]{2,5}-\d{4}-[A-Z0-9]{6}$")


async def create_event(
    db_session,
    *,
    created_by: StaffAccount,
    title: str,
    prefix: str,
    price: int,
    state: EventState = EventState.PUBLISHED,
    capacity: int | None = None,
    overflow_rule: OverflowRule = OverflowRule.HARD_REJECTION,
    custom_fields: list[EventFieldDefinition] | None = None,
) -> Event:
    event = Event(
        title=title,
        description=f"{title} description",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
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


def build_batch_payload(field_definition_id: str, *, acknowledge_duplicates: bool = False) -> dict:
    return {
        "submitter_name": "Chidi Okonkwo",
        "submitter_email": "submitter@example.com",
        "acknowledge_duplicates": acknowledge_duplicates,
        "participants": [
            {
                "first_name": "Ngozi",
                "last_name": "Eze",
                "email": "ngozi@example.com",
                "custom_field_values": [
                    {"field_definition_id": field_definition_id, "value": "+2348011111111"}
                ],
            },
            {
                "first_name": "Emeka",
                "last_name": "Obi",
                "email": "emeka@example.com",
                "custom_field_values": [
                    {"field_definition_id": field_definition_id, "value": "+2348022222222"}
                ],
            },
            {
                "first_name": "Fatima",
                "last_name": "Aliyu",
                "email": "fatima@example.com",
                "custom_field_values": [
                    {"field_definition_id": field_definition_id, "value": "+2348033333333"}
                ],
            },
            {
                "first_name": "Chinedu",
                "last_name": "Nwosu",
                "email": "chinedu@example.com",
                "custom_field_values": [
                    {"field_definition_id": field_definition_id, "value": "+2348044444444"}
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_free_event_registration_is_immediately_confirmed(
    client,
    db_session,
    seeded_free_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {
                    "field_definition_id": phone_field.id,
                    "value": "+2348012345678",
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "confirmed"
    assert body["is_free"] is True
    assert body["payment_url"] is None
    assert body["message"] == "Registration confirmed. A ticket has been sent to amina.bello@example.com."
    assert REG_ID_PATTERN.fullmatch(body["reg_id"])
    assert captured_email_tasks and captured_email_tasks[0]["to"] == ["amina.bello@example.com"]
    assert captured_email_tasks[0]["subject"] == "Your ticket for Community Meetup 2026"

    registration = (
        await db_session.execute(
            select(Registration).where(Registration.reg_id == body["reg_id"])
        )
    ).scalar_one()
    assert registration.state == RegistrationState.CONFIRMED

    payment = (await db_session.execute(select(Payment))).scalars().all()
    assert payment == []


@pytest.mark.asyncio
async def test_paid_event_registration_starts_as_pending_payment(
    client,
    db_session,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    phone_field = seeded_paid_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_paid_published_event.id}",
        json={
            "first_name": "Chidi",
            "last_name": "Okonkwo",
            "email": "chidi@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {
                    "field_definition_id": phone_field.id,
                    "value": "08012345678",
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "pending_payment"
    assert body["is_free"] is False
    assert body["message"] == "Registration created. Complete payment to confirm your spot."
    assert body["payment_url"].startswith("http://localhost:8000/mock-payment/pay?ref=MOCK_")
    assert captured_email_tasks == []

    payment = (await db_session.execute(select(Payment))).scalars().one()
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == 5000
    assert payment.payment_reference.startswith("MOCK_")


@pytest.mark.asyncio
async def test_duplicate_email_without_acknowledgement_returns_409(
    client,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]
    payload = {
        "first_name": "Amina",
        "last_name": "Bello",
        "email": "amina.bello@example.com",
        "acknowledge_duplicate": False,
        "custom_field_values": [
            {
                "field_definition_id": phone_field.id,
                "value": "+2348012345678",
            }
        ],
    }

    first_response = await client.post(f"/register/{seeded_free_published_event.id}", json=payload)
    second_response = await client.post(f"/register/{seeded_free_published_event.id}", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "This email has already been used to register for this event.",
        "duplicate_email": True,
    }


@pytest.mark.asyncio
async def test_duplicate_email_with_acknowledgement_proceeds(
    client,
    db_session,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    first_response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": phone_field.id, "value": "+2348012345678"}
            ],
        },
    )
    second_response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": True,
            "custom_field_values": [
                {"field_definition_id": phone_field.id, "value": "+2348012345678"}
            ],
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 2


@pytest.mark.asyncio
async def test_missing_required_custom_fields_returns_422(
    client,
    seeded_free_published_event: Event,
) -> None:
    response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Missing required custom fields: Phone Number."}


@pytest.mark.asyncio
async def test_invalid_phone_custom_field_returns_422(
    client,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": phone_field.id, "value": "not-a-phone"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Field 'Phone Number' must be a valid phone number."}


@pytest.mark.asyncio
async def test_invalid_number_custom_field_returns_422(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Numeric Workshop",
        prefix="NUM",
        price=0,
        custom_fields=[
            EventFieldDefinition(
                label="Experience Years",
                field_type=FieldType.NUMBER,
                is_required=True,
                display_order=1,
            )
        ],
    )
    number_field = event.field_definitions[0]

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Tolu",
            "last_name": "Ade",
            "email": "tolu@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": number_field.id, "value": "abc"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Field 'Experience Years' must be a valid numeric value."}


@pytest.mark.asyncio
async def test_invalid_date_custom_field_returns_422(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Date Workshop",
        prefix="DAT",
        price=0,
        custom_fields=[
            EventFieldDefinition(
                label="Arrival Date",
                field_type=FieldType.DATE,
                is_required=True,
                display_order=1,
            )
        ],
    )
    date_field = event.field_definitions[0]

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Tolu",
            "last_name": "Ade",
            "email": "tolu@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": date_field.id, "value": "2026-13-40"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Field 'Arrival Date' must be a valid ISO 8601 calendar date."}


@pytest.mark.asyncio
async def test_invalid_email_custom_field_returns_422(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Email Workshop",
        prefix="EML",
        price=0,
        custom_fields=[
            EventFieldDefinition(
                label="Alternate Email",
                field_type=FieldType.EMAIL,
                is_required=True,
                display_order=1,
            )
        ],
    )
    email_field = event.field_definitions[0]

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Tolu",
            "last_name": "Ade",
            "email": "tolu@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": email_field.id, "value": "not-an-email"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Field 'Alternate Email' must be a valid email address."}


@pytest.mark.asyncio
async def test_unknown_field_definition_id_returns_422(
    client,
    seeded_free_published_event: Event,
) -> None:
    response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": "fld_unknown", "value": "+2348012345678"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown field_definition_id(s): fld_unknown."}


@pytest.mark.asyncio
async def test_duplicate_custom_field_submission_returns_422(
    client,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_free_published_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [
                {"field_definition_id": phone_field.id, "value": "+2348012345678"},
                {"field_definition_id": phone_field.id, "value": "08012345678"},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": f"Duplicate submission for field_definition_id '{phone_field.id}'."
    }


@pytest.mark.asyncio
async def test_cancelled_event_rejects_new_registrations(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Cancelled Event",
        prefix="CNL",
        price=0,
        state=EventState.CANCELLED,
    )

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This event is no longer accepting registrations."}


@pytest.mark.asyncio
async def test_completed_event_rejects_new_registrations(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Completed Event",
        prefix="COM",
        price=0,
        state=EventState.COMPLETED,
    )

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This event is no longer accepting registrations."}


@pytest.mark.asyncio
async def test_draft_event_registration_returns_404(
    client,
    seeded_draft_event: Event,
) -> None:
    response = await client.post(
        f"/register/{seeded_draft_event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found."}


@pytest.mark.asyncio
async def test_full_event_with_hard_rejection_returns_409(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Limited Event",
        prefix="LIM",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    db_session.add(
        Registration(
            event_id=event.id,
            first_name="Taken",
            last_name="Seat",
            email="taken@example.com",
            reg_id="LIM-2026-ABC123",
            state=RegistrationState.CONFIRMED,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This event is fully booked and is not accepting further registrations."}


@pytest.mark.asyncio
async def test_full_event_with_waitlist_creates_waitlisted_registration(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Waitlist Event",
        prefix="WLT",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    db_session.add(
        Registration(
            event_id=event.id,
            first_name="Taken",
            last_name="Seat",
            email="taken@example.com",
            reg_id="WLT-2026-ABC123",
            state=RegistrationState.CONFIRMED,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Amina",
            "last_name": "Bello",
            "email": "amina.bello@example.com",
            "acknowledge_duplicate": False,
            "custom_field_values": [],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "waitlisted"
    assert body["payment_url"] is None
    assert body["message"] == "The event is full. You have been added to the waitlist."

    registration = (
        await db_session.execute(
            select(Registration).where(Registration.reg_id == body["reg_id"])
        )
    ).scalar_one()
    assert registration.state == RegistrationState.WAITLISTED
    assert registration.waitlist_position == 1


def test_registration_state_transition_rules() -> None:
    service = RegistrationService(session=None, settings=get_settings())  # type: ignore[arg-type]
    service.validate_state_transition(RegistrationState.PENDING_PAYMENT, RegistrationState.CONFIRMED)
    service.validate_state_transition(RegistrationState.CONFIRMED, RegistrationState.REFUND_REQUESTED)
    service.validate_state_transition(RegistrationState.WAITLISTED, RegistrationState.PENDING_PAYMENT)

    with pytest.raises(RegistrationValidationError, match="Invalid registration state transition"):
        service.validate_state_transition(RegistrationState.CONFIRMED, RegistrationState.FAILED)


@pytest.mark.asyncio
async def test_batch_registration_requires_minimum_of_four_participants(
    client,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]
    payload = build_batch_payload(phone_field.id)
    payload["participants"] = payload["participants"][:3]

    response = await client.post(f"/register/{seeded_free_published_event.id}/batch", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Batch registration requires a minimum of 4 participants."}


@pytest.mark.asyncio
async def test_free_batch_registration_is_immediately_confirmed(
    client,
    db_session,
    seeded_free_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_free_published_event.id}/batch",
        json=build_batch_payload(phone_field.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "confirmed"
    assert body["total_amount"] == 0
    assert body["currency"] == "NGN"
    assert body["participant_count"] == 4
    assert body["payment_url"] is None
    assert body["message"] == "Batch registration confirmed. Tickets have been sent to all participants."
    assert len(body["participants"]) == 4
    assert len({participant["reg_id"] for participant in body["participants"]}) == 4
    assert all(REG_ID_PATTERN.fullmatch(participant["reg_id"]) for participant in body["participants"])
    assert len(captured_email_tasks) == 4
    assert {payload["to"][0] for payload in captured_email_tasks} == {
        "ngozi@example.com",
        "emeka@example.com",
        "fatima@example.com",
        "chinedu@example.com",
    }

    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 4
    assert all(registration.state == RegistrationState.CONFIRMED for registration in registrations)
    assert (await db_session.execute(select(func.count(Payment.id)))).scalar_one() == 0

    batches = (await db_session.execute(select(BatchRegistration))).scalars().all()
    assert len(batches) == 1
    assert batches[0].submitter_email == "submitter@example.com"


@pytest.mark.asyncio
async def test_paid_batch_registration_starts_as_pending_payment(
    client,
    db_session,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    phone_field = seeded_paid_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_paid_published_event.id}/batch",
        json=build_batch_payload(phone_field.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "pending_payment"
    assert body["total_amount"] == 20000
    assert body["participant_count"] == 4
    assert body["payment_url"].startswith("http://localhost:8000/mock-payment/pay?ref=MOCK_")
    assert body["message"] == "Batch registration created. Complete payment to confirm all spots."
    assert len(captured_email_tasks) == 0

    payments = (await db_session.execute(select(Payment))).scalars().all()
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.PENDING
    assert payments[0].amount == 20000
    assert payments[0].batch_id is not None

    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 4
    assert all(registration.state == RegistrationState.PENDING_PAYMENT for registration in registrations)
    assert len({registration.batch_id for registration in registrations}) == 1
    assert registrations[0].batch_id == payments[0].batch_id


@pytest.mark.asyncio
async def test_batch_submitter_is_not_registered_unless_included_as_participant(
    client,
    db_session,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]

    response = await client.post(
        f"/register/{seeded_free_published_event.id}/batch",
        json=build_batch_payload(phone_field.id),
    )

    assert response.status_code == 201

    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 4
    assert all(registration.email != "submitter@example.com" for registration in registrations)


@pytest.mark.asyncio
async def test_intra_batch_duplicate_emails_return_422_and_create_no_records(
    client,
    db_session,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]
    payload = build_batch_payload(phone_field.id)
    payload["participants"][3]["email"] = "ngozi@example.com"

    response = await client.post(f"/register/{seeded_free_published_event.id}/batch", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Duplicate emails found within this batch. Each participant must have a unique email address.",
        "duplicate_emails": ["ngozi@example.com"],
    }
    assert (await db_session.execute(select(func.count(Registration.id)))).scalar_one() == 0
    assert (await db_session.execute(select(func.count(BatchRegistration.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_cross_registration_duplicate_without_acknowledgement_returns_409_and_creates_no_records(
    client,
    db_session,
    seeded_free_published_event: Event,
) -> None:
    phone_field = seeded_free_published_event.field_definitions[0]
    db_session.add(
        Registration(
            event_id=seeded_free_published_event.id,
            first_name="Existing",
            last_name="Registrant",
            email="ngozi@example.com",
            reg_id="CMT-2026-ABC123",
            state=RegistrationState.CONFIRMED,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/register/{seeded_free_published_event.id}/batch",
        json=build_batch_payload(phone_field.id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "One or more participants are already registered for this event. Re-submit with acknowledge_duplicates: true to proceed.",
        "duplicate_emails": ["ngozi@example.com"],
        "duplicate_warning": True,
    }
    assert (await db_session.execute(select(func.count(BatchRegistration.id)))).scalar_one() == 0
    assert (await db_session.execute(select(func.count(Registration.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_cross_registration_duplicate_with_acknowledgement_proceeds(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    phone_field = seeded_paid_published_event.field_definitions[0]
    db_session.add(
        Registration(
            event_id=seeded_paid_published_event.id,
            first_name="Existing",
            last_name="Registrant",
            email="ngozi@example.com",
            reg_id="TEC-2026-ABC123",
            state=RegistrationState.CONFIRMED,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/register/{seeded_paid_published_event.id}/batch",
        json=build_batch_payload(phone_field.id, acknowledge_duplicates=True),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "pending_payment"
    assert len(body["participants"]) == 4

    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 5
    assert sum(1 for registration in registrations if registration.email == "ngozi@example.com") == 2
