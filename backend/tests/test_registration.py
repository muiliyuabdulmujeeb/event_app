from __future__ import annotations

from datetime import datetime, timezone
import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import RegistrationValidationError
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.payment import Payment, PaymentStatus
from app.models.registration import Registration, RegistrationState
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
    assert captured_email_tasks and captured_email_tasks[0]["to"] == "amina.bello@example.com"

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

    with pytest.raises(RegistrationValidationError, match="Invalid registration state transition"):
        service.validate_state_transition(RegistrationState.CONFIRMED, RegistrationState.FAILED)
