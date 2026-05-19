from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.event import Event, EventState, OverflowRule
from app.models.notification import UserNotification
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccount


async def admin_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "admin@eventapp.local", "password": "Admin1234!"},
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
    state: EventState = EventState.PUBLISHED,
) -> Event:
    event = Event(
        title=title,
        description=f"{title} description",
        event_date=datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix=prefix,
        price=price,
        capacity=capacity,
        overflow_rule=overflow_rule,
        state=state,
        created_by=created_by.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


async def create_registration(
    db_session,
    *,
    event: Event,
    reg_id: str,
    email: str,
    state: RegistrationState,
    waitlist_position: int | None = None,
    payment_status: PaymentStatus | None = None,
    is_checked_in: bool = False,
) -> Registration:
    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Bello",
        email=email,
        reg_id=reg_id,
        state=state,
        waitlist_position=waitlist_position,
        is_checked_in=is_checked_in,
        checked_in_at=(
            datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
            if is_checked_in
            else None
        ),
    )
    db_session.add(registration)
    await db_session.flush()
    if payment_status is not None:
        payment = Payment(
            gateway=PaymentGateway.MOCK,
            payment_reference=f"MOCK_{reg_id.replace('-', '')}",
            amount=event.price,
            currency="NGN",
            status=payment_status,
            registration_id=registration.id,
            attempt_number=1,
            paid_at=(
                datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
                if payment_status == PaymentStatus.SUCCESSFUL
                else None
            ),
        )
        db_session.add(payment)
        await db_session.flush()
        registration.current_payment_id = payment.id
    await db_session.commit()
    await db_session.refresh(registration)
    return registration


@pytest.mark.asyncio
async def test_confirmed_free_registration_can_be_cancelled_and_promotes_next_waitlisted_user(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Free Cancel Event",
        prefix="FCE",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    confirmed = await create_registration(
        db_session,
        event=event,
        reg_id="FCE-2026-CNF001",
        email="confirmed@example.com",
        state=RegistrationState.CONFIRMED,
    )
    waitlisted = await create_registration(
        db_session,
        event=event,
        reg_id="FCE-2026-WTL001",
        email="waitlisted@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )

    response = await client.patch(
        f"/registrations/{confirmed.reg_id}/cancel",
        json={"reason": "Unable to attend"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reg_id": confirmed.reg_id,
        "state": "cancelled",
        "was_waitlisted": False,
        "previous_waitlist_position": None,
        "cancellation_reason": "user_cancelled",
        "message": "Registration cancelled successfully.",
    }

    confirmed_id = confirmed.id
    waitlisted_id = waitlisted.id
    await db_session.rollback()
    db_session.expire_all()
    confirmed = (await db_session.execute(select(Registration).where(Registration.id == confirmed_id))).scalar_one()
    waitlisted = (await db_session.execute(select(Registration).where(Registration.id == waitlisted_id))).scalar_one()
    assert confirmed.state == RegistrationState.CANCELLED
    assert waitlisted.state == RegistrationState.CONFIRMED
    assert waitlisted.waitlist_position is None
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["waitlisted@example.com"]


@pytest.mark.asyncio
async def test_pending_payment_registration_can_be_cancelled_and_payment_is_marked_failed(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Paid Cancel Event",
        prefix="PCE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="PCE-2026-PND001",
        email="pending@example.com",
        state=RegistrationState.PENDING_PAYMENT,
        payment_status=PaymentStatus.PENDING,
    )

    response = await client.patch(
        f"/registrations/{registration.reg_id}/cancel",
        json={"reason": "Changed plans"},
    )

    assert response.status_code == 200
    event_id = event.id
    registration_id = registration.id
    await db_session.rollback()
    db_session.expire_all()
    registration = (
        await db_session.execute(
            select(Registration).where(Registration.id == registration_id)
        )
    ).scalar_one()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert registration.state == RegistrationState.CANCELLED
    assert payment.status == PaymentStatus.FAILED

    reregister_response = await client.post(
        f"/register/{event_id}",
        json={
            "first_name": "New",
            "last_name": "Registrant",
            "email": "new@example.com",
            "custom_field_values": [],
        },
    )
    assert reregister_response.status_code == 201
    assert reregister_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_waitlisted_registration_can_be_cancelled_with_history_preserved_and_queue_resequenced(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Waitlist Cancel Event",
        prefix="WCE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    first_waitlisted = await create_registration(
        db_session,
        event=event,
        reg_id="WCE-2026-WTL001",
        email="first@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    second_waitlisted = await create_registration(
        db_session,
        event=event,
        reg_id="WCE-2026-WTL002",
        email="second@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=2,
    )

    response = await client.patch(
        f"/registrations/{first_waitlisted.reg_id}/cancel",
        json={"reason": "No longer interested"},
    )

    assert response.status_code == 200
    assert response.json()["was_waitlisted"] is True
    assert response.json()["previous_waitlist_position"] == 1
    assert response.json()["cancellation_reason"] == "user_cancelled"

    first_waitlisted_id = first_waitlisted.id
    second_waitlisted_id = second_waitlisted.id
    await db_session.rollback()
    db_session.expire_all()
    first_waitlisted = (
        await db_session.execute(select(Registration).where(Registration.id == first_waitlisted_id))
    ).scalar_one()
    second_waitlisted = (
        await db_session.execute(select(Registration).where(Registration.id == second_waitlisted_id))
    ).scalar_one()
    assert first_waitlisted.state == RegistrationState.CANCELLED
    assert first_waitlisted.was_waitlisted is True
    assert first_waitlisted.previous_waitlist_position == 1
    assert first_waitlisted.waitlist_position is None
    assert second_waitlisted.waitlist_position == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [RegistrationState.FAILED, RegistrationState.CANCELLED])
async def test_failed_or_cancelled_registration_cannot_be_cancelled_again(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    state: RegistrationState,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Blocked Cancel Event",
        prefix="BCE",
        price=0,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id=f"BCE-2026-{state.value[:3].upper()}001",
        email=f"{state.value}@example.com",
        state=state,
    )

    response = await client.patch(
        f"/registrations/{registration.reg_id}/cancel",
        json={"reason": "Retry"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This registration cannot be cancelled in its current state."}


@pytest.mark.asyncio
async def test_checked_in_registration_cannot_be_cancelled(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Checked In Event",
        prefix="CHK",
        price=0,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="CHK-2026-CNF001",
        email="checkedin@example.com",
        state=RegistrationState.CONFIRMED,
        is_checked_in=True,
    )

    response = await client.patch(
        f"/registrations/{registration.reg_id}/cancel",
        json={"reason": "Late cancellation"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Checked-in registrations cannot be cancelled."}


@pytest.mark.asyncio
async def test_refund_request_requires_cancelled_registration_and_successful_payment_history(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Refund Rules Event",
        prefix="RRE",
        price=5000,
        capacity=10,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    active_registration = await create_registration(
        db_session,
        event=event,
        reg_id="RRE-2026-CNF001",
        email="active@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )
    cancelled_without_payment = await create_registration(
        db_session,
        event=event,
        reg_id="RRE-2026-CAN001",
        email="nopayment@example.com",
        state=RegistrationState.CANCELLED,
    )

    not_cancelled_response = await client.post(
        f"/registrations/{active_registration.reg_id}/refund-requests",
        json={"reason": "Please refund me"},
    )
    assert not_cancelled_response.status_code == 409
    assert not_cancelled_response.json() == {"detail": "Only cancelled registrations can request a refund."}

    missing_payment_response = await client.post(
        f"/registrations/{cancelled_without_payment.reg_id}/refund-requests",
        json={"reason": "Please refund me"},
    )
    assert missing_payment_response.status_code == 409
    assert missing_payment_response.json() == {
        "detail": "Refund requests are only available for registrations with successful payment history."
    }


@pytest.mark.asyncio
async def test_refund_request_creation_lookup_and_duplicate_blocking_follow_requested_status(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Refund Lookup Event",
        prefix="RLE",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="RLE-2026-CNF001",
        email="refund@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )

    cancel_response = await client.patch(
        f"/registrations/{registration.reg_id}/cancel",
        json={"reason": "Cannot attend"},
    )
    assert cancel_response.status_code == 200

    refund_response = await client.post(
        f"/registrations/{registration.reg_id}/refund-requests",
        json={"reason": "Refund requested after cancellation"},
    )
    assert refund_response.status_code == 201
    refund_request_id = refund_response.json()["refund_request_id"]

    duplicate_refund_response = await client.post(
        f"/registrations/{registration.reg_id}/refund-requests",
        json={"reason": "Second attempt"},
    )
    assert duplicate_refund_response.status_code == 409
    assert duplicate_refund_response.json() == {
        "detail": "An active refund request already exists for this registration."
    }

    lookup_response = await client.get("/registrations/lookup", params={"reg_id": registration.reg_id})
    assert lookup_response.status_code == 200
    assert lookup_response.json()["refund_request"] == {
        "id": refund_request_id,
        "status": "requested",
        "requested_at": lookup_response.json()["refund_request"]["requested_at"],
        "processed_at": None,
    }

    reregister_response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Refund",
            "last_name": "Registrant",
            "email": registration.email,
            "custom_field_values": [],
        },
    )
    assert reregister_response.status_code == 409
    assert reregister_response.json() == {
        "detail": "This email has already been used to register for this event.",
        "duplicate_email": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("final_status", ["completed", "rejected"])
async def test_completed_or_rejected_refund_request_allows_reregistration(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    final_status: str,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title=f"Re-register {final_status.title()} Event",
        prefix="RRG",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id=f"RRG-2026-{final_status[:3].upper()}001",
        email=f"{final_status}@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )
    assert (await client.patch(f"/registrations/{registration.reg_id}/cancel", json={})).status_code == 200
    refund_create_response = await client.post(
        f"/registrations/{registration.reg_id}/refund-requests",
        json={"reason": "Requesting refund"},
    )
    assert refund_create_response.status_code == 201
    refund_request_id = refund_create_response.json()["refund_request_id"]

    update_response = await client.patch(
        f"/admin/refund-requests/{refund_request_id}",
        headers=await admin_headers(client),
        json={
            "status": final_status,
            "notification_method": "in_app",
            "message_body": f"Refund {final_status}.",
            "title": f"Refund {final_status.title()}",
            "resolution_notes": f"{final_status.title()} by admin.",
        },
    )
    assert update_response.status_code == 200

    reregister_response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "Return",
            "last_name": "Registrant",
            "email": registration.email,
            "custom_field_values": [],
        },
    )
    assert reregister_response.status_code == 201
    assert reregister_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_admin_can_list_and_update_refund_requests_and_create_user_notification(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Admin Refund Event",
        prefix="ARE",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="ARE-2026-CNF001",
        email="adminrefund@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )
    assert (await client.patch(f"/registrations/{registration.reg_id}/cancel", json={})).status_code == 200
    refund_create_response = await client.post(
        f"/registrations/{registration.reg_id}/refund-requests",
        json={"reason": "Please process"},
    )
    refund_request_id = refund_create_response.json()["refund_request_id"]

    list_response = await client.get(
        "/admin/refund-requests",
        headers=await admin_headers(client),
        params={"status": "requested", "event_id": event.id, "reg_id": registration.reg_id},
    )
    assert list_response.status_code == 200
    assert list_response.json() == {
        "items": [
            {
                "refund_request_id": refund_request_id,
                "reg_id": registration.reg_id,
                "status": "requested",
                "requested_at": list_response.json()["items"][0]["requested_at"],
                "processed_at": None,
            }
        ],
        "total": 1,
    }

    update_response = await client.patch(
        f"/admin/refund-requests/{refund_request_id}",
        headers=await admin_headers(client),
        json={
            "status": "approved",
            "notification_method": "in_app",
            "message_body": "Your refund request has been approved.",
            "title": "Refund Approved",
            "resolution_notes": "Approved by finance.",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json() == {
        "refund_request_id": refund_request_id,
        "reg_id": registration.reg_id,
        "status": "approved",
        "processed_at": update_response.json()["processed_at"],
        "message": "Refund request updated successfully.",
    }

    admin_id = seeded_admin_account.id
    registration_reg_id = registration.reg_id
    await db_session.rollback()
    db_session.expire_all()
    refund_request = (await db_session.execute(select(RefundRequest))).scalar_one()
    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()
    assert refund_request.status == RefundRequestStatus.APPROVED
    assert refund_request.processed_by_staff_id == admin_id
    assert len(user_notifications) == 1
    assert user_notifications[0].reg_id == registration_reg_id
    assert user_notifications[0].title == "Refund Approved"
