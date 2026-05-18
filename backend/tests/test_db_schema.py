from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.event import Event, EventState, OverflowRule
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccount, StaffRole


def test_initial_migration_applied(sync_engine) -> None:
    with sync_engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert revision == "20260517_01"


def test_expected_tables_exist(sync_engine) -> None:
    inspector = inspect(sync_engine)
    table_names = set(inspector.get_table_names())

    expected_tables = {
        "batch_registrations",
        "event_field_definitions",
        "events",
        "payments",
        "refresh_tokens",
        "registration_field_values",
        "registrations",
        "staff_access_mode",
        "staff_accounts",
        "staff_event_access",
        "staff_notifications",
        "user_notifications",
        "waitlist_promotion_offers",
    }

    assert expected_tables.issubset(table_names)
    assert "waitlist" not in table_names


@pytest.mark.asyncio
async def test_event_price_zero_computes_is_free(db_session) -> None:
    admin = StaffAccount(
        email="admin.phase2@example.com",
        password_hash="hashed",
        role=StaffRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()

    event = Event(
        title="Community Meetup 2026",
        description="Free event",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        location="Lagos",
        prefix="CMT",
        price=0,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.DRAFT,
        created_by=admin.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.is_free is True


@pytest.mark.asyncio
async def test_invalid_event_prefix_violates_database_constraint(db_session) -> None:
    admin = StaffAccount(
        email="prefix.phase2@example.com",
        password_hash="hashed",
        role=StaffRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()

    event = Event(
        title="Broken Prefix Event",
        description="Should fail",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        location="Abuja",
        prefix="te-1",
        price=1000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.DRAFT,
        created_by=admin.id,
    )
    db_session.add(event)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_unique_constraints_for_registration_and_payment(db_session) -> None:
    admin = StaffAccount(
        email="unique.phase2@example.com",
        password_hash="hashed",
        role=StaffRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()

    event = Event(
        title="Tech Conference 2026",
        description="Paid event",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        location="Lagos",
        prefix="TEC",
        price=5000,
        capacity=100,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.PUBLISHED,
        created_by=admin.id,
    )
    db_session.add(event)
    await db_session.flush()

    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Bello",
        email="amina@example.com",
        reg_id="TEC-2026-ABC123",
        state=RegistrationState.CONFIRMED,
    )
    db_session.add(registration)
    await db_session.flush()

    payment = Payment(
        gateway=PaymentGateway.MOCK,
        payment_reference="MOCK_REF_001",
        amount=5000,
        currency="NGN",
        status=PaymentStatus.SUCCESSFUL,
        registration_id=registration.id,
    )
    db_session.add(payment)
    await db_session.commit()
    registration_id = registration.id

    duplicate_registration = Registration(
        event_id=event.id,
        first_name="Fatima",
        last_name="Aliyu",
        email="fatima@example.com",
        reg_id="TEC-2026-ABC123",
        state=RegistrationState.PENDING_PAYMENT,
    )
    db_session.add(duplicate_registration)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()

    duplicate_payment = Payment(
        gateway=PaymentGateway.MOCK,
        payment_reference="MOCK_REF_001",
        amount=5000,
        currency="NGN",
        status=PaymentStatus.PENDING,
        registration_id=registration_id,
    )
    db_session.add(duplicate_payment)

    with pytest.raises(IntegrityError):
        await db_session.commit()
