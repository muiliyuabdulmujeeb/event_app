from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventFieldDefinition, EventState, OverflowRule
from app.models.notification import StaffNotification, UserNotification
from app.models.payment import Payment, PaymentGateway, PaymentStatus
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


async def create_registration(
    db_session,
    *,
    event: Event,
    reg_id: str,
    email: str,
    state: RegistrationState,
    waitlist_position: int | None = None,
    payment_status: PaymentStatus | None = None,
    payment_amount: int | None = None,
) -> Registration:
    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Bello",
        email=email,
        reg_id=reg_id,
        state=state,
        waitlist_position=waitlist_position,
    )
    db_session.add(registration)
    await db_session.flush()

    if payment_status is not None:
        db_session.add(
            Payment(
                gateway=PaymentGateway.MOCK,
                payment_reference=f"MOCK_{reg_id.replace('-', '')}",
                amount=payment_amount if payment_amount is not None else event.price,
                currency="NGN",
                status=payment_status,
                registration_id=registration.id,
                paid_at=(
                    datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc)
                    if payment_status == PaymentStatus.SUCCESSFUL
                    else None
                ),
            )
        )

    await db_session.commit()
    await db_session.refresh(registration)
    return registration


@pytest.mark.asyncio
async def test_registration_lookup_returns_unseen_notifications_and_mark_seen_hides_them(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-LOOK01",
        email="lookup@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )
    unseen = UserNotification(
        reg_id=registration.reg_id,
        title="Event Update",
        body="The venue has changed.",
        is_seen=False,
    )
    seen = UserNotification(
        reg_id=registration.reg_id,
        title="Old Notice",
        body="Already acknowledged.",
        is_seen=True,
    )
    db_session.add_all([unseen, seen])
    await db_session.commit()

    lookup_response = await client.get(
        "/registrations/lookup",
        params={"reg_id": registration.reg_id},
    )

    assert lookup_response.status_code == 200
    body = lookup_response.json()
    assert body["registration"]["reg_id"] == registration.reg_id
    assert body["payment"] == {
        "status": "successful",
        "amount_paid": seeded_paid_published_event.price,
        "currency": "NGN",
        "paid_at": "2026-05-16T09:00:00Z",
    }
    assert body["notifications"] == [
        {
            "id": unseen.id,
            "title": "Event Update",
            "body": "The venue has changed.",
            "is_seen": False,
            "created_at": body["notifications"][0]["created_at"],
        }
    ]

    seen_response = await client.patch(f"/registrations/notifications/{unseen.id}/seen")
    assert seen_response.status_code == 200
    assert seen_response.json() == {"id": unseen.id, "is_seen": True}

    second_lookup = await client.get(
        "/registrations/lookup",
        params={"reg_id": registration.reg_id},
    )
    assert second_lookup.status_code == 200
    assert second_lookup.json()["notifications"] == []


@pytest.mark.asyncio
async def test_registration_lookup_returns_404_for_unknown_reg_id(client) -> None:
    response = await client.get("/registrations/lookup", params={"reg_id": "TEC-2026-MISSING"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No registration found for the provided reg_id."}


@pytest.mark.asyncio
async def test_marking_unknown_user_notification_seen_returns_404(client) -> None:
    response = await client.patch("/registrations/notifications/unt_missing/seen")

    assert response.status_code == 404
    assert response.json() == {"detail": "User notification not found."}


@pytest.mark.asyncio
async def test_event_cancellation_cancels_confirmed_and_pending_payment_and_dispatches_notifications(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    confirmed_registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-CAN001",
        email="confirmed@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )
    pending_registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-CAN002",
        email="pending@example.com",
        state=RegistrationState.PENDING_PAYMENT,
        payment_status=PaymentStatus.PENDING,
    )

    response = await client.patch(
        f"/admin/events/{seeded_paid_published_event.id}/state",
        headers=await admin_headers(client),
        json={
            "state": "cancelled",
            "notification_method": "email",
            "notification_body": "This event has been cancelled due to unforeseen circumstances.",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"

    confirmed_registration_id = confirmed_registration.id
    pending_registration_id = pending_registration.id
    confirmed_registration_reg_id = confirmed_registration.reg_id
    admin_staff_id = seeded_admin_account.id
    regular_staff_id = seeded_staff_account.id
    await db_session.rollback()
    db_session.expire_all()
    confirmed_registration = (
        await db_session.execute(select(Registration).where(Registration.id == confirmed_registration_id))
    ).scalar_one()
    pending_registration = (
        await db_session.execute(select(Registration).where(Registration.id == pending_registration_id))
    ).scalar_one()
    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()

    assert confirmed_registration.state == RegistrationState.CANCELLED
    assert pending_registration.state == RegistrationState.CANCELLED
    assert [(notification.reg_id, notification.title) for notification in user_notifications] == [
        (confirmed_registration_reg_id, "Event Cancelled")
    ]
    assert len(staff_notifications) == 2
    assert {notification.staff_id for notification in staff_notifications} == {
        admin_staff_id,
        regular_staff_id,
    }
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["confirmed@example.com"]
    assert captured_email_tasks[0]["subject"] == "Event Cancelled"


@pytest.mark.asyncio
async def test_price_change_applied_to_existing_confirmed_registrations_creates_in_app_notifications_without_changing_historical_payments(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    first_registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-PRC001",
        email="first@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
        payment_amount=5000,
    )
    second_registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-PRC002",
        email="second@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
        payment_amount=5000,
    )

    response = await client.patch(
        f"/admin/events/{seeded_paid_published_event.id}",
        headers=await admin_headers(client),
        json={
            "price": 7000,
            "price_change_scope": "all_existing_confirmed",
            "notification_method": "in_app",
            "notification_body": "The ticket price has been updated for this event.",
        },
    )

    assert response.status_code == 200
    assert response.json()["price"] == 7000

    first_reg_id = first_registration.reg_id
    second_reg_id = second_registration.reg_id
    admin_staff_id = seeded_admin_account.id
    regular_staff_id = seeded_staff_account.id
    await db_session.rollback()
    db_session.expire_all()
    user_notifications = (await db_session.execute(select(UserNotification).order_by(UserNotification.reg_id))).scalars().all()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()
    payments = (await db_session.execute(select(Payment).order_by(Payment.payment_reference))).scalars().all()

    assert [(notification.reg_id, notification.title) for notification in user_notifications] == [
        (first_reg_id, "Price Updated"),
        (second_reg_id, "Price Updated"),
    ]
    assert len(staff_notifications) == 2
    assert {notification.staff_id for notification in staff_notifications} == {
        admin_staff_id,
        regular_staff_id,
    }
    assert all(payment.amount == 5000 for payment in payments)
    assert captured_email_tasks == []


@pytest.mark.asyncio
async def test_admin_custom_price_change_email_notification_sends_emails_only(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-NTF001",
        email="notify@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )

    response = await client.post(
        "/admin/notifications",
        headers=await admin_headers(client),
        json={
            "notification_type": "price_change",
            "notification_method": "email",
            "event_id": seeded_paid_published_event.id,
            "body": "The event price has changed. Please review the update.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "notification_type": "price_change",
        "notification_method": "email",
        "user_notifications_created": 0,
        "staff_notifications_created": 0,
        "email_recipients_count": 1,
        "message": "Notification sent successfully.",
    }

    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()
    assert user_notifications == []
    assert staff_notifications == []
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["notify@example.com"]
    assert captured_email_tasks[0]["subject"] == "Price Updated"


@pytest.mark.asyncio
async def test_refund_request_releases_capacity_and_promotes_next_waitlisted_registration_on_free_event(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Refund Waitlist Event",
        prefix="RWL",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    confirmed_registration = await create_registration(
        db_session,
        event=event,
        reg_id="RWL-2026-CNF001",
        email="confirmed@example.com",
        state=RegistrationState.CONFIRMED,
    )
    promoted_registration = await create_registration(
        db_session,
        event=event,
        reg_id="RWL-2026-WTL001",
        email="promote@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    remaining_waitlist = await create_registration(
        db_session,
        event=event,
        reg_id="RWL-2026-WTL002",
        email="stillwait@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=2,
    )

    response = await client.patch(
        f"/admin/registrations/{confirmed_registration.reg_id}/refund",
        headers=await admin_headers(client),
        json={
            "state": "refund_requested",
            "notification_method": "in_app",
            "message_body": "Your refund request has been recorded.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reg_id": confirmed_registration.reg_id,
        "state": "refund_requested",
    }

    confirmed_registration_id = confirmed_registration.id
    promoted_registration_id = promoted_registration.id
    remaining_waitlist_id = remaining_waitlist.id
    confirmed_registration_reg_id = confirmed_registration.reg_id
    admin_staff_id = seeded_admin_account.id
    regular_staff_id = seeded_staff_account.id
    await db_session.rollback()
    db_session.expire_all()
    confirmed_registration = (
        await db_session.execute(select(Registration).where(Registration.id == confirmed_registration_id))
    ).scalar_one()
    promoted_registration = (
        await db_session.execute(select(Registration).where(Registration.id == promoted_registration_id))
    ).scalar_one()
    remaining_waitlist = (
        await db_session.execute(select(Registration).where(Registration.id == remaining_waitlist_id))
    ).scalar_one()
    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()

    assert confirmed_registration.state == RegistrationState.REFUND_REQUESTED
    assert promoted_registration.state == RegistrationState.CONFIRMED
    assert promoted_registration.waitlist_position is None
    assert remaining_waitlist.state == RegistrationState.WAITLISTED
    assert remaining_waitlist.waitlist_position == 1
    assert len(user_notifications) == 1
    assert user_notifications[0].reg_id == confirmed_registration_reg_id
    assert len(staff_notifications) == 2
    assert {notification.staff_id for notification in staff_notifications} == {
        admin_staff_id,
        regular_staff_id,
    }
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["promote@example.com"]
    assert captured_email_tasks[0]["subject"] == "Your ticket for Refund Waitlist Event"


@pytest.mark.asyncio
async def test_refund_requested_no_longer_consumes_capacity_for_paid_events(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Refund Capacity Event",
        prefix="RFC",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="RFC-2026-CNF001",
        email="holder@example.com",
        state=RegistrationState.CONFIRMED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )

    refund_response = await client.patch(
        f"/admin/registrations/{registration.reg_id}/refund",
        headers=await admin_headers(client),
        json={
            "state": "refund_requested",
            "notification_method": "email",
            "message_body": "Your refund request has been started.",
        },
    )
    assert refund_response.status_code == 200

    new_registration_response = await client.post(
        f"/register/{event.id}",
        json={
            "first_name": "New",
            "last_name": "Registrant",
            "email": "new@example.com",
            "custom_field_values": [],
        },
    )

    assert new_registration_response.status_code == 201
    assert new_registration_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_refund_processed_email_sends_email_without_creating_in_app_notifications(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
    captured_email_tasks: list[dict],
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        reg_id="TEC-2026-RFD001",
        email="refund@example.com",
        state=RegistrationState.REFUND_REQUESTED,
        payment_status=PaymentStatus.SUCCESSFUL,
    )

    response = await client.patch(
        f"/admin/registrations/{registration.reg_id}/refund",
        headers=await admin_headers(client),
        json={
            "state": "refunded",
            "notification_method": "email",
            "message_body": "Your refund has been completed.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reg_id": registration.reg_id,
        "state": "refunded",
    }

    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()
    assert user_notifications == []
    assert staff_notifications == []
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["refund@example.com"]
    assert captured_email_tasks[0]["subject"] == "Refund Processed"
