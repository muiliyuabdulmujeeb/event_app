from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestedBy, RefundRequestStatus
from app.models.registration import BatchRegistration, Registration, RegistrationFieldValue, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffRole


@dataclass(frozen=True)
class AnalyticsDataset:
    paid_event: Event
    unlimited_event: Event
    company_field: EventFieldDefinition
    role_field: EventFieldDefinition
    waived_registration_reg_id: str
    refunded_registration_reg_id: str
    waitlisted_registration_reg_id: str


async def auth_headers(client, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def ensure_staff_account(
    db_session: AsyncSession,
    *,
    email: str,
    password: str,
    role: StaffRole,
) -> StaffAccount:
    account = StaffAccount(
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()
    db_session.add(StaffAccessModeRecord(staff_id=account.id, mode=StaffAccessMode.ALL_EVENTS))
    await db_session.commit()
    await db_session.refresh(account)
    return account


async def build_analytics_dataset(
    db_session: AsyncSession,
    *,
    admin_account: StaffAccount,
) -> AnalyticsDataset:
    company_field = EventFieldDefinition(
        label="Company",
        field_type=FieldType.TEXT,
        is_required=False,
        display_order=1,
    )
    paid_event = Event(
        title="Paid Analytics Event",
        description="Primary event for analytics coverage.",
        event_date=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix="PAE",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.WAITLIST,
        state=EventState.PUBLISHED,
        created_by=admin_account.id,
    )
    paid_event.created_at = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    paid_event.field_definitions = [company_field]

    role_field = EventFieldDefinition(
        label="Role",
        field_type=FieldType.TEXT,
        is_required=False,
        display_order=1,
    )
    unlimited_event = Event(
        title="Unlimited Analytics Event",
        description="Secondary event for joined analytics coverage.",
        event_date=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        location="Abuja, Nigeria",
        prefix="UAE",
        price=3000,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.PUBLISHED,
        created_by=admin_account.id,
    )
    unlimited_event.created_at = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    unlimited_event.field_definitions = [role_field]

    db_session.add_all([paid_event, unlimited_event])
    await db_session.flush()

    confirmed = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-CNF001",
        email="confirmed@example.com",
        state=RegistrationState.CONFIRMED,
        registered_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
        checked_in=True,
        custom_fields={company_field.id: "Alpha"},
    )
    await _attach_single_payment(
        db_session,
        registration=confirmed,
        amount=5000,
        status=PaymentStatus.SUCCESSFUL,
        payment_reference="MOCK_PAE_CNF001",
        paid_at=datetime(2026, 5, 1, 9, 15, tzinfo=timezone.utc),
    )

    refunded = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-CAN001",
        email="refund@example.com",
        state=RegistrationState.CANCELLED,
        registered_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        custom_fields={company_field.id: "Acme"},
    )
    await _attach_single_payment(
        db_session,
        registration=refunded,
        amount=5000,
        status=PaymentStatus.SUCCESSFUL,
        payment_reference="MOCK_PAE_CAN001",
        paid_at=datetime(2026, 5, 2, 9, 20, tzinfo=timezone.utc),
    )
    db_session.add(
        RefundRequest(
            registration_id=refunded.id,
            status=RefundRequestStatus.COMPLETED,
            requested_by=RefundRequestedBy.PUBLIC,
            reason="Unable to attend",
            requested_at=datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc),
            processed_at=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
        )
    )

    failed = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-FLD001",
        email="failed@example.com",
        state=RegistrationState.FAILED,
        registered_at=datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc),
        custom_fields={company_field.id: "Beta"},
    )
    await _attach_single_payment(
        db_session,
        registration=failed,
        amount=5000,
        status=PaymentStatus.FAILED,
        payment_reference="MOCK_PAE_FLD001",
        paid_at=None,
    )

    waitlisted = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-WTL001",
        email="waitlisted@example.com",
        state=RegistrationState.WAITLISTED,
        registered_at=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
        waitlist_position=1,
        custom_fields={company_field.id: "Gamma"},
    )

    pending = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-PND001",
        email="pending@example.com",
        state=RegistrationState.PENDING_PAYMENT,
        registered_at=datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc),
        custom_fields={company_field.id: "Delta"},
    )
    await _attach_single_payment(
        db_session,
        registration=pending,
        amount=5000,
        status=PaymentStatus.PENDING,
        payment_reference="MOCK_PAE_PND001",
        paid_at=None,
    )

    batch_registration = BatchRegistration(
        event_id=paid_event.id,
        submitter_name="Batch Submitter",
        submitter_email="batch.submitter@example.com",
        total_amount=20000,
    )
    db_session.add(batch_registration)
    await db_session.flush()
    db_session.add(
        Payment(
            gateway=PaymentGateway.MOCK,
            payment_reference="MOCK_BATCH_PAE_001",
            amount=20000,
            currency="NGN",
            status=PaymentStatus.SUCCESSFUL,
            batch_id=batch_registration.id,
            paid_at=datetime(2026, 5, 6, 9, 30, tzinfo=timezone.utc),
        )
    )
    for index, company in enumerate(["BatchCo A", "BatchCo B", "BatchCo C", "BatchCo D"], start=1):
        await _create_registration(
            db_session,
            event=paid_event,
            reg_id=f"PAE-2026-BAT00{index}",
            email=f"batch{index}@example.com",
            state=RegistrationState.CONFIRMED,
            registered_at=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
            batch_id=batch_registration.id,
            custom_fields={company_field.id: company},
        )

    waived = await _create_registration(
        db_session,
        event=paid_event,
        reg_id="PAE-2026-EXC001",
        email="waived@example.com",
        state=RegistrationState.CONFIRMED,
        registered_at=datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc),
        custom_fields={company_field.id: "VIPCo"},
    )
    db_session.add(
        ExceptionRegistrationOffer(
            event_id=paid_event.id,
            issued_by_staff_id=admin_account.id,
            target_email=waived.email,
            payment_waived=True,
            capacity_override=True,
            expires_at=datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc),
            status=ExceptionRegistrationOfferStatus.USED,
            used_registration_id=waived.id,
        )
    )

    second_event_registration = await _create_registration(
        db_session,
        event=unlimited_event,
        reg_id="UAE-2026-CNF001",
        email="unlimited@example.com",
        state=RegistrationState.CONFIRMED,
        registered_at=datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc),
        custom_fields={role_field.id: "Speaker"},
    )
    await _attach_single_payment(
        db_session,
        registration=second_event_registration,
        amount=3000,
        status=PaymentStatus.SUCCESSFUL,
        payment_reference="MOCK_UAE_CNF001",
        paid_at=datetime(2026, 5, 8, 9, 10, tzinfo=timezone.utc),
    )

    await db_session.commit()
    return AnalyticsDataset(
        paid_event=paid_event,
        unlimited_event=unlimited_event,
        company_field=company_field,
        role_field=role_field,
        waived_registration_reg_id=waived.reg_id,
        refunded_registration_reg_id=refunded.reg_id,
        waitlisted_registration_reg_id=waitlisted.reg_id,
    )


async def _create_registration(
    db_session: AsyncSession,
    *,
    event: Event,
    reg_id: str,
    email: str,
    state: RegistrationState,
    registered_at: datetime,
    custom_fields: dict[str, str],
    checked_in: bool = False,
    waitlist_position: int | None = None,
    batch_id: str | None = None,
) -> Registration:
    registration = Registration(
        event_id=event.id,
        first_name=reg_id.split("-")[-1],
        last_name="Registrant",
        email=email,
        reg_id=reg_id,
        state=state,
        is_checked_in=checked_in,
        checked_in_at=datetime(2026, 5, 10, 8, 0, tzinfo=timezone.utc) if checked_in else None,
        waitlist_position=waitlist_position,
        batch_id=batch_id,
        registered_at=registered_at,
    )
    db_session.add(registration)
    await db_session.flush()
    for field_definition_id, value in custom_fields.items():
        db_session.add(
            RegistrationFieldValue(
                registration_id=registration.id,
                field_definition_id=field_definition_id,
                value=value,
            )
        )
    await db_session.flush()
    return registration


async def _attach_single_payment(
    db_session: AsyncSession,
    *,
    registration: Registration,
    amount: int,
    status: PaymentStatus,
    payment_reference: str,
    paid_at: datetime | None,
) -> None:
    payment = Payment(
        gateway=PaymentGateway.MOCK,
        payment_reference=payment_reference,
        amount=amount,
        currency="NGN",
        status=status,
        registration_id=registration.id,
        attempt_number=1,
        paid_at=paid_at,
    )
    db_session.add(payment)
    await db_session.flush()
    registration.current_payment_id = payment.id
    await db_session.flush()
