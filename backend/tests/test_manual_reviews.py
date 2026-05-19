from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.event import Event, EventState, OverflowRule
from app.models.manual_review_case import ManualReviewCase, ManualReviewCaseStatus, ManualReviewCaseType
from app.models.notification import StaffNotification, UserNotification
from app.models.payment import Payment, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessModeRecord, StaffAccount, StaffEventAccess


async def admin_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "admin@eventapp.local", "password": "Admin1234!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def staff_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "staff@eventapp.local", "password": "Staff1234!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_event(
    db_session,
    *,
    created_by: StaffAccount,
    title: str,
    prefix: str,
    price: int,
    capacity: int | None,
    overflow_rule: OverflowRule,
) -> Event:
    event = Event(
        title=title,
        description=f"{title} description",
        event_date=datetime(2026, 12, 5, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix=prefix,
        price=price,
        capacity=capacity,
        overflow_rule=overflow_rule,
        state=EventState.PUBLISHED,
        created_by=created_by.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


async def create_manual_review_case(
    db_session,
    *,
    event_id: str,
    registration: Registration | None = None,
    payment: Payment | None = None,
) -> ManualReviewCase:
    case = ManualReviewCase(
        event_id=event_id,
        registration_id=registration.id if registration is not None else None,
        payment_id=payment.id if payment is not None else None,
        case_type=ManualReviewCaseType.OTHER,
        status=ManualReviewCaseStatus.OPEN,
        summary="Manual follow-up required",
        details="Created for test coverage.",
        created_by_system=True,
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case


async def create_paid_pending_registration(client, db_session, event: Event, *, email: str, first_name: str = "Amina") -> Registration:
    response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": first_name,
            "last_name": "Bello",
            "email": email,
            "custom_field_values": [],
        },
    )
    assert response.status_code == 201
    registration = (
        await db_session.execute(select(Registration).where(Registration.email == email))
    ).scalar_one()
    return registration


async def grant_staff_authorization(
    client,
    *,
    event_id: str,
    staff_id: str,
    can_manage_manual_reviews: bool = False,
    can_requeue_registrations: bool = False,
) -> None:
    response = await client.put(
        f"/admin/events/{event_id}/authorizations/{staff_id}",
        headers=await admin_headers(client),
        json={
            "can_manage_manual_reviews": can_manage_manual_reviews,
            "can_requeue_registrations": can_requeue_registrations,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_late_payment_success_creates_manual_review_case_and_notifications(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Late Success Review Event",
        prefix="LSR",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_paid_pending_registration(
        client,
        db_session,
        event,
        email="late-review@example.com",
    )
    payment = (await db_session.execute(select(Payment))).scalar_one()

    fail_response = await client.post(f"/mock-payment/fail/{payment.payment_reference}")
    confirm_response = await client.post(f"/mock-payment/confirm/{payment.payment_reference}")

    assert fail_response.status_code == 200
    assert confirm_response.status_code == 200

    registration_id = registration.id
    payment_id = payment.id
    admin_id = seeded_admin_account.id
    staff_id = seeded_staff_account.id
    await db_session.rollback()
    db_session.expire_all()
    registration = (await db_session.execute(select(Registration).where(Registration.id == registration_id))).scalar_one()
    payment = (await db_session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()
    case = (await db_session.execute(select(ManualReviewCase))).scalar_one()
    notifications = (await db_session.execute(select(StaffNotification))).scalars().all()

    assert registration.state == RegistrationState.FAILED
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert case.case_type == ManualReviewCaseType.LATE_PAYMENT_SUCCESS
    assert case.status == ManualReviewCaseStatus.OPEN
    assert case.payment_id == payment_id
    assert case.registration_id == registration_id
    assert case.created_by_system is True
    assert len(notifications) == 2
    assert {notification.staff_id for notification in notifications} == {admin_id, staff_id}
    assert captured_email_tasks == []


@pytest.mark.asyncio
async def test_admin_can_list_get_and_resolve_manual_review_cases(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Admin Review Event",
        prefix="AREV",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    case = await create_manual_review_case(db_session, event_id=event.id)

    list_response = await client.get(
        "/staff/manual-reviews",
        headers=await admin_headers(client),
        params={"status": "open"},
    )
    detail_response = await client.get(
        f"/staff/manual-reviews/{case.id}",
        headers=await admin_headers(client),
    )
    update_response = await client.patch(
        f"/staff/manual-reviews/{case.id}",
        headers=await admin_headers(client),
        json={
            "status": "resolved",
            "resolution_action": "documented",
            "resolution_notes": "Reviewed and closed by admin.",
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["cases"][0]["id"] == case.id
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == case.id
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "resolved"
    assert update_response.json()["resolution_action"] == "documented"
    assert update_response.json()["resolution_notes"] == "Reviewed and closed by admin."


@pytest.mark.asyncio
async def test_staff_requires_explicit_manual_review_authorization_to_access_case(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Staff Review Access Event",
        prefix="SRA",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    case = await create_manual_review_case(db_session, event_id=event.id)

    forbidden_response = await client.get(
        f"/staff/manual-reviews/{case.id}",
        headers=await staff_headers(client),
    )
    assert forbidden_response.status_code == 403

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    allowed_response = await client.get(
        f"/staff/manual-reviews/{case.id}",
        headers=await staff_headers(client),
    )
    assert allowed_response.status_code == 200
    assert allowed_response.json()["id"] == case.id


@pytest.mark.asyncio
async def test_staff_with_manual_review_permission_but_without_event_access_cannot_access_case(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Selected Access Review Event",
        prefix="SAR",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    case = await create_manual_review_case(db_session, event_id=event.id)

    access_mode = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_mode.mode = "selected_events"
    await db_session.commit()

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    response = await client.get(
        f"/staff/manual-reviews/{case.id}",
        headers=await staff_headers(client),
    )
    assert response.status_code == 403

    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=event.id))
    await db_session.commit()

    allowed_response = await client.get(
        f"/staff/manual-reviews/{case.id}",
        headers=await staff_headers(client),
    )
    assert allowed_response.status_code == 200


@pytest.mark.asyncio
async def test_requeue_creates_fresh_payment_attempt_and_notifies_user(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Requeue Attempt Event",
        prefix="RAT",
        price=5000,
        capacity=2,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_paid_pending_registration(
        client,
        db_session,
        event,
        email="requeue@example.com",
    )
    original_payment = (await db_session.execute(select(Payment))).scalar_one()
    assert (await client.post(f"/mock-payment/fail/{original_payment.payment_reference}")).status_code == 200
    captured_email_tasks.clear()

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/requeue",
        headers=await admin_headers(client),
        json={"reason": "Retry approved", "notify_user": True},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "pending_payment"

    registration_id = registration.id
    reg_id = registration.reg_id
    await db_session.rollback()
    db_session.expire_all()
    registration = (await db_session.execute(select(Registration).where(Registration.id == registration_id))).scalar_one()
    payments = (
        await db_session.execute(
            select(Payment).where(Payment.registration_id == registration_id).order_by(Payment.attempt_number)
        )
    ).scalars().all()
    case = (await db_session.execute(select(ManualReviewCase))).scalar_one()
    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()

    assert registration.state == RegistrationState.PENDING_PAYMENT
    assert registration.current_payment_id == payments[-1].id
    assert [payment.attempt_number for payment in payments] == [1, 2]
    assert payments[0].status == PaymentStatus.FAILED
    assert payments[1].status == PaymentStatus.PENDING
    assert case.status == ManualReviewCaseStatus.RESOLVED
    assert case.resolution_action == "requeue_registration"
    assert case.registration_id == registration_id
    assert len(user_notifications) == 1
    assert f"/registrations/{reg_id}/payments/initialize" in user_notifications[0].body
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["requeue@example.com"]
    assert f"/registrations/{reg_id}/payments/initialize" in captured_email_tasks[0]["text_body"]


@pytest.mark.asyncio
async def test_authorized_staff_can_requeue_and_public_initialize_uses_new_attempt(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Staff Requeue Event",
        prefix="SRE",
        price=5000,
        capacity=2,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_paid_pending_registration(
        client,
        db_session,
        event,
        email="staffrequeue@example.com",
    )
    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert (await client.post(f"/mock-payment/fail/{payment.payment_reference}")).status_code == 200

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_requeue_registrations=True,
    )

    requeue_response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/requeue",
        headers=await staff_headers(client),
        json={"reason": "Retry for customer", "notify_user": False},
    )
    assert requeue_response.status_code == 200

    initialize_response = await client.post(f"/registrations/{registration.reg_id}/payments/initialize")
    assert initialize_response.status_code == 200
    body = initialize_response.json()
    assert body["message"] == "Payment initialized successfully."
    assert body["payment_reference"].endswith("_A2")
    assert body["checkout_url"].endswith(body["payment_reference"])

    second_initialize = await client.post(f"/registrations/{registration.reg_id}/payments/initialize")
    assert second_initialize.status_code == 200
    assert second_initialize.json() == body

    registration_id = registration.id
    await db_session.rollback()
    db_session.expire_all()
    payments = (
        await db_session.execute(
            select(Payment).where(Payment.registration_id == registration_id).order_by(Payment.attempt_number)
        )
    ).scalars().all()
    registration = (await db_session.execute(select(Registration).where(Registration.id == registration_id))).scalar_one()

    assert len(payments) == 2
    assert payments[-1].gateway_checkout_url == body["checkout_url"]
    assert registration.current_payment_id == payments[-1].id


@pytest.mark.asyncio
async def test_requeue_rejects_invalid_targets_and_capacity_conflicts(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    free_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Free Requeue Event",
        prefix="FRE",
        price=0,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    free_registration = Registration(
        event_id=free_event.id,
        first_name="Free",
        last_name="User",
        email="free@example.com",
        reg_id="FRE-2026-REG001",
        state=RegistrationState.FAILED,
    )
    db_session.add(free_registration)
    await db_session.commit()

    free_response = await client.patch(
        f"/staff/registrations/{free_registration.reg_id}/requeue",
        headers=await admin_headers(client),
        json={"reason": "Should fail", "notify_user": False},
    )
    assert free_response.status_code == 422

    paid_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Busy Requeue Event",
        prefix="BRE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    failed_registration = await create_paid_pending_registration(
        client,
        db_session,
        event=paid_event,
        email="failed@example.com",
    )
    failed_payment = (await db_session.execute(select(Payment))).scalar_one()
    assert (await client.post(f"/mock-payment/fail/{failed_payment.payment_reference}")).status_code == 200

    occupying_registration = Registration(
        event_id=paid_event.id,
        first_name="Busy",
        last_name="Registrant",
        email="busy@example.com",
        reg_id="BRE-2026-CNF001",
        state=RegistrationState.CONFIRMED,
    )
    db_session.add(occupying_registration)
    await db_session.commit()

    capacity_response = await client.patch(
        f"/staff/registrations/{failed_registration.reg_id}/requeue",
        headers=await admin_headers(client),
        json={"reason": "Retry blocked", "notify_user": False},
    )
    assert capacity_response.status_code == 409

    confirmed_response = await client.patch(
        f"/staff/registrations/{occupying_registration.reg_id}/requeue",
        headers=await admin_headers(client),
        json={"reason": "Wrong state", "notify_user": False},
    )
    assert confirmed_response.status_code == 409
