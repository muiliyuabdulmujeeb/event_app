from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventState, OverflowRule
from app.models.notification import StaffNotification, UserNotification
from app.models.payment import Payment, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffEventAccess
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus
from app.workers.waitlist_promotion_tasks import _expire_stale_waitlist_promotion_offers


async def auth_headers(client, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
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
        event_date=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
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


async def create_registration(
    db_session,
    *,
    event: Event,
    reg_id: str,
    email: str,
    state: RegistrationState,
    waitlist_position: int | None = None,
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
    await db_session.commit()
    await db_session.refresh(registration)
    return registration


@pytest.mark.asyncio
async def test_admin_can_manually_promote_paid_waitlisted_registration_and_notify_user(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Paid Waitlist Event",
        prefix="PWT",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    promoted_registration = await create_registration(
        db_session,
        event=event,
        reg_id="PWT-2026-WTL001",
        email="promote@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    remaining_waitlist = await create_registration(
        db_session,
        event=event,
        reg_id="PWT-2026-WTL002",
        email="stillwait@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=2,
    )
    custom_expiry = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    response = await client.patch(
        f"/staff/registrations/{promoted_registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"offer_expires_at": custom_expiry.isoformat().replace("+00:00", "Z")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reg_id"] == promoted_registration.reg_id
    assert body["state"] == "pending_payment"
    assert body["promotion_offer_status"] == "offered"
    assert body["offer_expires_at"] == "2026-10-21T12:00:00Z"
    assert body["payment_action_url"].startswith("http://localhost:8000/registrations/payment-offers/")
    assert body["payment_action_url"].endswith("/initialize")

    promoted_registration_id = promoted_registration.id
    remaining_waitlist_id = remaining_waitlist.id
    await db_session.rollback()
    db_session.expire_all()
    promoted_registration = (
        await db_session.execute(select(Registration).where(Registration.id == promoted_registration_id))
    ).scalar_one()
    remaining_waitlist = (
        await db_session.execute(select(Registration).where(Registration.id == remaining_waitlist_id))
    ).scalar_one()
    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    user_notifications = (await db_session.execute(select(UserNotification))).scalars().all()

    assert promoted_registration.state == RegistrationState.PENDING_PAYMENT
    assert promoted_registration.waitlist_position is None
    assert remaining_waitlist.state == RegistrationState.WAITLISTED
    assert remaining_waitlist.waitlist_position == 1
    assert offer.status == WaitlistPromotionOfferStatus.OFFERED
    assert offer.payment_id is None
    assert len(offer.public_token) == 26
    assert (await db_session.execute(select(func.count(Payment.id)))).scalar_one() == 0
    assert len(user_notifications) == 1
    assert user_notifications[0].reg_id == promoted_registration.reg_id
    assert body["payment_action_url"] in user_notifications[0].body
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["promote@example.com"]
    assert captured_email_tasks[0]["subject"] == "Payment link for your spot at Paid Waitlist Event"
    assert body["payment_action_url"] in captured_email_tasks[0]["text_body"]


@pytest.mark.asyncio
async def test_lookup_returns_active_paid_waitlist_promotion_offer_details(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Lookup Waitlist Event",
        prefix="LWP",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="LWP-2026-WTL001",
        email="lookupwait@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    promote_response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={},
    )
    assert promote_response.status_code == 200

    lookup_response = await client.get("/registrations/lookup", params={"reg_id": registration.reg_id})

    assert lookup_response.status_code == 200
    body = lookup_response.json()
    assert body["registration"]["state"] == "pending_payment"
    assert body["payment"] is None
    assert body["promotion_offer"]["status"] == "offered"
    assert body["promotion_offer"]["payment_action_url"].endswith("/initialize")
    assert len(body["notifications"]) == 1
    assert body["promotion_offer"]["payment_action_url"] in body["notifications"][0]["body"]


@pytest.mark.asyncio
async def test_payment_offer_initialization_happens_only_when_internal_link_is_clicked(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Promotion Init Event",
        prefix="PIF",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="PIF-2026-WTL001",
        email="init@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={},
    )
    assert response.status_code == 200
    captured_email_tasks.clear()

    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    offer_id = offer.id
    assert (await db_session.execute(select(func.count(Payment.id)))).scalar_one() == 0

    first_init = await client.get(
        f"/registrations/payment-offers/{offer.public_token}/initialize",
        follow_redirects=False,
    )

    assert first_init.status_code == 307
    assert first_init.headers["location"].startswith("http://localhost:8000/mock-payment/pay?ref=MOCK_")

    await db_session.rollback()
    db_session.expire_all()
    offer = (
        await db_session.execute(
            select(WaitlistPromotionOffer)
            .where(WaitlistPromotionOffer.id == offer_id)
            .options(selectinload(WaitlistPromotionOffer.payment))
        )
    ).scalar_one()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert offer.status == WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED
    assert offer.payment_id == payment.id
    assert offer.gateway_checkout_url == first_init.headers["location"]
    assert payment.status == PaymentStatus.PENDING
    assert len(captured_email_tasks) == 0

    second_init = await client.get(
        f"/registrations/payment-offers/{offer.public_token}/initialize",
        follow_redirects=False,
    )
    assert second_init.status_code == 307
    assert second_init.headers["location"] == first_init.headers["location"]
    assert (await db_session.execute(select(func.count(Payment.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_expired_payment_offer_initialization_marks_registration_failed_and_releases_capacity(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Expired Offer Event",
        prefix="EOF",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="EOF-2026-WTL001",
        email="expired@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    promote_response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={},
    )
    assert promote_response.status_code == 200
    captured_email_tasks.clear()

    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    offer.offer_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    event_id = event.id

    init_response = await client.get(
        f"/registrations/payment-offers/{offer.public_token}/initialize",
        follow_redirects=False,
    )

    assert init_response.status_code == 409
    assert init_response.json() == {"detail": "This payment offer has expired."}

    await db_session.rollback()
    db_session.expire_all()
    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    assert offer.status == WaitlistPromotionOfferStatus.EXPIRED
    assert registration.state == RegistrationState.FAILED
    assert (await db_session.execute(select(func.count(Payment.id)))).scalar_one() == 0

    new_registration_response = await client.post(
        f"/register/{event_id}",
        json={
            "first_name": "New",
            "last_name": "Registrant",
            "email": "newslot@example.com",
            "custom_field_values": [],
        },
    )
    assert new_registration_response.status_code == 201
    assert new_registration_response.json()["state"] == "pending_payment"


@pytest.mark.asyncio
async def test_paid_event_cancellation_does_not_auto_promote_waitlisted_registration(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="No Auto Promote Paid Event",
        prefix="NAP",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    confirmed = await create_registration(
        db_session,
        event=event,
        reg_id="NAP-2026-CNF001",
        email="confirmed@example.com",
        state=RegistrationState.CONFIRMED,
    )
    waitlisted = await create_registration(
        db_session,
        event=event,
        reg_id="NAP-2026-WTL001",
        email="waitlisted@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )

    response = await client.patch(f"/registrations/{confirmed.reg_id}/cancel", json={})

    assert response.status_code == 200

    waitlisted_id = waitlisted.id
    await db_session.rollback()
    db_session.expire_all()
    waitlisted = (
        await db_session.execute(select(Registration).where(Registration.id == waitlisted_id))
    ).scalar_one()
    offers = (await db_session.execute(select(WaitlistPromotionOffer))).scalars().all()
    assert waitlisted.state == RegistrationState.WAITLISTED
    assert waitlisted.waitlist_position == 1
    assert offers == []
    assert captured_email_tasks == []


@pytest.mark.asyncio
async def test_staff_with_selected_event_access_can_promote_but_cannot_set_custom_expiry(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Selected Access Event",
        prefix="SEL",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="SEL-2026-WTL001",
        email="selected@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    access_mode_record = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_mode_record.mode = StaffAccessMode.SELECTED_EVENTS
    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=event.id))
    await db_session.commit()

    promote_response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="staff@eventapp.local", password="Staff1234!"),
        json={},
    )
    assert promote_response.status_code == 200
    assert promote_response.json()["state"] == "pending_payment"
    assert len(captured_email_tasks) == 1

    another_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Custom Expiry Event",
        prefix="SCE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    another_registration = await create_registration(
        db_session,
        event=another_event,
        reg_id="SCE-2026-WTL001",
        email="customexpiry@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=another_event.id))
    await db_session.commit()

    custom_expiry_response = await client.patch(
        f"/staff/registrations/{another_registration.reg_id}/promote",
        headers=await auth_headers(client, email="staff@eventapp.local", password="Staff1234!"),
        json={"offer_expires_at": "2026-10-21T12:00:00Z"},
    )
    assert custom_expiry_response.status_code == 403
    assert custom_expiry_response.json() == {"detail": "Only admin users can set a custom offer expiry."}


@pytest.mark.asyncio
async def test_staff_cannot_promote_waitlisted_registration_for_inaccessible_event(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Forbidden Access Event",
        prefix="FOR",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="FOR-2026-WTL001",
        email="forbidden@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    access_mode_record = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_mode_record.mode = StaffAccessMode.SELECTED_EVENTS
    await db_session.commit()

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="staff@eventapp.local", password="Staff1234!"),
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have access to registrations for this event."}


@pytest.mark.asyncio
async def test_cancelled_former_waitlist_registration_cannot_be_promoted_after_overflow_rule_change(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Historical Waitlist Promotion Event",
        prefix="HWP",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="HWP-2026-WTL001",
        email="historical.promote@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    overflow_response = await client.patch(
        f"/admin/events/{event.id}/overflow-rule",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"overflow_rule": "hard_rejection", "reason": "Close waitlist."},
    )
    assert overflow_response.status_code == 200

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only waitlisted registrations can be promoted."}


@pytest.mark.asyncio
async def test_expired_initialized_offer_marks_late_success_for_manual_review(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Late Success Promotion Event",
        prefix="LSP",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.WAITLIST,
    )
    registration = await create_registration(
        db_session,
        event=event,
        reg_id="LSP-2026-WTL001",
        email="latesuccess@example.com",
        state=RegistrationState.WAITLISTED,
        waitlist_position=1,
    )
    promote_response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/promote",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={},
    )
    assert promote_response.status_code == 200
    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    captured_email_tasks.clear()

    init_response = await client.get(
        f"/registrations/payment-offers/{offer.public_token}/initialize",
        follow_redirects=False,
    )
    assert init_response.status_code == 307

    registration_reg_id = registration.reg_id
    admin_staff_id = seeded_admin_account.id
    regular_staff_id = seeded_staff_account.id
    await db_session.rollback()
    db_session.expire_all()
    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    offer.offer_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    expiry_results = await _expire_stale_waitlist_promotion_offers()
    assert expiry_results == [
        {
            "public_token": offer.public_token,
            "reg_id": registration_reg_id,
            "status": "expired",
        }
    ]

    confirm_response = await client.post(f"/mock-payment/confirm/{payment.payment_reference}")
    assert confirm_response.status_code == 200

    await db_session.rollback()
    db_session.expire_all()
    registration = (await db_session.execute(select(Registration))).scalar_one()
    offer = (await db_session.execute(select(WaitlistPromotionOffer))).scalar_one()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    staff_notifications = (await db_session.execute(select(StaffNotification))).scalars().all()

    assert registration.state == RegistrationState.FAILED
    assert offer.status == WaitlistPromotionOfferStatus.MANUAL_REVIEW
    assert payment.status == PaymentStatus.SUCCESSFUL
    assert len(staff_notifications) == 2
    assert {notification.staff_id for notification in staff_notifications} == {
        admin_staff_id,
        regular_staff_id,
    }
    assert all(notification.title == "Manual Payment Review Required" for notification in staff_notifications)
    assert captured_email_tasks == []
