from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.models.event import Event, EventState, OverflowRule
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.exception_registration_offer_audit import (
    ExceptionRegistrationOfferAudit,
    ExceptionRegistrationOfferAuditAction,
)
from app.models.payment import Payment, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestedBy, RefundRequestStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffRole


async def auth_headers(client, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_account(
    db_session,
    *,
    email: str,
    role: StaffRole,
    password: str,
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
        event_date=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
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
) -> Registration:
    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Bello",
        email=email,
        reg_id=reg_id,
        state=state,
    )
    db_session.add(registration)
    await db_session.commit()
    await db_session.refresh(registration)
    return registration


@pytest.mark.asyncio
async def test_event_creator_can_issue_exception_offer_and_view_audit(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Creator Offer Event",
        prefix="COE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )

    response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "vip@example.com",
            "target_first_name": "Jane",
            "target_last_name": "Doe",
            "source_reg_id": "COE-2026-ABC123",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "note": "VIP guest",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["event_id"] == event.id
    assert body["target_email"] == "vip@example.com"
    assert body["payment_waived"] is True
    assert body["capacity_override"] is True
    assert body["status"] == "issued"
    assert body["registration_action_url"].endswith(f"/registrations/exception-offers/{body['public_token']}/register")

    audit_response = await client.get(
        f"/admin/events/{event.id}/exception-offers/{body['id']}/audit",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
    )

    assert audit_response.status_code == 200
    assert audit_response.json() == {
        "offer_id": body["id"],
        "entries": [
            {
                "action": "issued",
                "actor_type": "staff",
                "actor_staff_id": seeded_admin_account.id,
                "details": "VIP guest",
                "created_at": audit_response.json()["entries"][0]["created_at"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_delegated_admin_can_issue_exception_offer_but_unauthorized_admin_cannot(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Delegated Offer Event",
        prefix="DOE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    delegated_admin = await create_account(
        db_session,
        email="delegated-admin@example.com",
        role=StaffRole.ADMIN,
        password="Delegated1234!",
    )
    blocked_admin = await create_account(
        db_session,
        email="blocked-admin@example.com",
        role=StaffRole.ADMIN,
        password="Blocked1234!",
    )

    grant_response = await client.put(
        f"/admin/events/{event.id}/authorizations/{delegated_admin.id}",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"can_manage_exception_offers": True},
    )
    assert grant_response.status_code == 200

    delegated_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email=delegated_admin.email, password="Delegated1234!"),
        json={
            "target_email": "delegated@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    blocked_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email=blocked_admin.email, password="Blocked1234!"),
        json={
            "target_email": "blocked@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    assert delegated_response.status_code == 201
    assert blocked_response.status_code == 403
    assert blocked_response.json() == {
        "detail": "You do not have permission to manage exception registration offers for this event."
    }


@pytest.mark.asyncio
async def test_admin_with_only_overflow_permission_cannot_issue_exception_offer(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Overflow Only Delegate Event",
        prefix="ODE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    delegated_admin = await create_account(
        db_session,
        email="overflow-only-admin@example.com",
        role=StaffRole.ADMIN,
        password="Overflow1234!",
    )
    grant_response = await client.put(
        f"/admin/events/{event.id}/authorizations/{delegated_admin.id}",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"can_change_overflow_rule": True},
    )
    assert grant_response.status_code == 200

    response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email=delegated_admin.email, password="Overflow1234!"),
        json={
            "target_email": "overflow@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to manage exception registration offers for this event."
    }


@pytest.mark.asyncio
async def test_staff_cannot_issue_exception_offer(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Staff Blocked Event",
        prefix="SBE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )

    response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="staff@eventapp.local", password="Staff1234!"),
        json={
            "target_email": "staffblocked@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to perform this action."}


@pytest.mark.asyncio
async def test_offer_list_filters_by_status_and_target_email(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Offer List Event",
        prefix="OLE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    creator_headers = await auth_headers(client, email="admin@eventapp.local", password="Admin1234!")

    issued_offer = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=creator_headers,
        json={
            "target_email": "issued@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    assert issued_offer.status_code == 201
    used_offer = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=creator_headers,
        json={
            "target_email": "used@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    assert used_offer.status_code == 201
    use_response = await client.post(
        f"/registrations/exception-offers/{used_offer.json()['public_token']}/register",
        json={
            "first_name": "Used",
            "last_name": "Offer",
            "email": "used@example.com",
            "custom_field_values": [],
        },
    )
    assert use_response.status_code == 201

    filtered_response = await client.get(
        f"/admin/events/{event.id}/exception-offers",
        headers=creator_headers,
        params={"status": "used", "target_email": "used@example.com"},
    )

    assert filtered_response.status_code == 200
    body = filtered_response.json()
    assert body["total"] == 1
    assert body["offers"][0]["target_email"] == "used@example.com"
    assert body["offers"][0]["status"] == "used"


@pytest.mark.asyncio
async def test_event_creator_can_revoke_offer_and_revoke_is_audited(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Revoke Offer Event",
        prefix="ROE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "revoke@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    offer_id = create_response.json()["id"]

    revoke_response = await client.patch(
        f"/admin/events/{event.id}/exception-offers/{offer_id}/revoke",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"reason": "Issued in error"},
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json() == {
        "id": offer_id,
        "status": "revoked",
    }

    audit_entries = (
        await db_session.execute(
            select(ExceptionRegistrationOfferAudit)
            .join(ExceptionRegistrationOffer, ExceptionRegistrationOffer.id == ExceptionRegistrationOfferAudit.offer_id)
            .where(ExceptionRegistrationOffer.id == offer_id)
            .order_by(ExceptionRegistrationOfferAudit.created_at.asc())
        )
    ).scalars().all()
    assert [entry.action for entry in audit_entries] == [
        ExceptionRegistrationOfferAuditAction.ISSUED,
        ExceptionRegistrationOfferAuditAction.REVOKED,
    ]
    assert audit_entries[1].details == "Issued in error"


@pytest.mark.asyncio
async def test_full_paid_event_allows_non_waived_exception_registration_and_tracks_capacity_override_count(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Full Paid Event",
        prefix="FPE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    await create_registration(
        db_session,
        event=event,
        reg_id="FPE-2026-CNF001",
        email="filled@example.com",
        state=RegistrationState.CONFIRMED,
    )
    create_offer_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "priority@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    offer = create_offer_response.json()
    event_id = event.id

    register_response = await client.post(
        f"/registrations/exception-offers/{offer['public_token']}/register",
        json={
            "first_name": "Priority",
            "last_name": "Guest",
            "email": "priority@example.com",
            "custom_field_values": [],
        },
    )

    assert register_response.status_code == 201
    body = register_response.json()
    assert body["state"] == "pending_payment"
    assert body["payment_waived"] is False
    assert body["payment_action_url"].endswith(
        f"/registrations/exception-offers/{offer['public_token']}/payments/initialize"
    )
    assert captured_email_tasks == []

    await db_session.rollback()
    db_session.expire_all()
    offer_record = (
        await db_session.execute(
            select(ExceptionRegistrationOffer)
            .where(ExceptionRegistrationOffer.id == offer["id"])
            .options(selectinload(ExceptionRegistrationOffer.used_registration))
        )
    ).scalar_one()
    payment = (await db_session.execute(select(Payment))).scalar_one()
    assert offer_record.status == ExceptionRegistrationOfferStatus.USED
    assert offer_record.used_registration is not None
    assert offer_record.used_registration.state == RegistrationState.PENDING_PAYMENT
    assert payment.status == PaymentStatus.PENDING
    assert offer_record.gateway_checkout_url is None

    detail_response = await client.get(
        f"/admin/events/{event_id}",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
    )
    search_response = await client.get(
        "/staff/registrations",
        headers=await auth_headers(client, email="staff@eventapp.local", password="Staff1234!"),
        params={"reg_id": body["reg_id"]},
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["capacity_override_count"] == 1
    assert search_response.status_code == 200
    assert search_response.json()["registrations"][0]["event"]["capacity_override_count"] == 1


@pytest.mark.asyncio
async def test_full_free_event_allows_exception_registration_and_counts_capacity_override(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Full Free Event",
        prefix="FFE",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    await create_registration(
        db_session,
        event=event,
        reg_id="FFE-2026-CNF001",
        email="freefilled@example.com",
        state=RegistrationState.CONFIRMED,
    )
    create_offer_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "freepriority@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = create_offer_response.json()["public_token"]

    register_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Free",
            "last_name": "Priority",
            "email": "freepriority@example.com",
            "custom_field_values": [],
        },
    )

    assert register_response.status_code == 201
    assert register_response.json()["state"] == "confirmed"
    assert register_response.json()["payment_action_url"] is None
    assert len(captured_email_tasks) == 1

    detail_response = await client.get(
        f"/admin/events/{event.id}",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["capacity_override_count"] == 1


@pytest.mark.asyncio
async def test_exception_offer_payment_initialization_happens_only_when_link_is_clicked(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Deferred Payment Event",
        prefix="DPE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    offer_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "deferred@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = offer_response.json()["public_token"]
    register_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Deferred",
            "last_name": "Guest",
            "email": "deferred@example.com",
            "custom_field_values": [],
        },
    )
    assert register_response.status_code == 201

    before_init_payment = (await db_session.execute(select(Payment))).scalar_one()
    assert before_init_payment.status == PaymentStatus.PENDING
    offer_record = (await db_session.execute(select(ExceptionRegistrationOffer))).scalar_one()
    assert offer_record.gateway_checkout_url is None

    first_init = await client.get(
        f"/registrations/exception-offers/{token}/payments/initialize",
        follow_redirects=False,
    )
    assert first_init.status_code == 307
    assert first_init.headers["location"].startswith("http://localhost:8000/mock-payment/pay?ref=MOCK_")

    await db_session.rollback()
    db_session.expire_all()
    offer_record = (await db_session.execute(select(ExceptionRegistrationOffer))).scalar_one()
    assert offer_record.gateway_checkout_url == first_init.headers["location"]

    second_init = await client.get(
        f"/registrations/exception-offers/{token}/payments/initialize",
        follow_redirects=False,
    )
    assert second_init.status_code == 307
    assert second_init.headers["location"] == first_init.headers["location"]
    payments = (await db_session.execute(select(Payment))).scalars().all()
    assert len(payments) == 1


@pytest.mark.asyncio
async def test_paid_waived_exception_offer_confirms_immediately_without_payment(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    captured_email_tasks: list[dict],
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Waived Payment Event",
        prefix="WPE",
        price=5000,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    offer_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "waived@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = offer_response.json()["public_token"]

    register_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Waived",
            "last_name": "Guest",
            "email": "waived@example.com",
            "custom_field_values": [],
        },
    )

    assert register_response.status_code == 201
    body = register_response.json()
    assert body == {
        "reg_id": body["reg_id"],
        "state": "confirmed",
        "payment_waived": True,
        "payment_action_url": None,
        "message": "Registration confirmed via exception offer.",
    }
    assert (await db_session.execute(select(Payment))).scalars().all() == []
    assert len(captured_email_tasks) == 1
    assert captured_email_tasks[0]["to"] == ["waived@example.com"]


@pytest.mark.asyncio
async def test_expired_offer_cannot_be_consumed_and_expiry_is_audited(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Expired Offer Event",
        prefix="EXO",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "expired@example.com",
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    assert create_response.status_code == 422

    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "expired@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = create_response.json()["public_token"]
    offer_id = create_response.json()["id"]
    offer_record = (await db_session.execute(select(ExceptionRegistrationOffer))).scalar_one()
    offer_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    consume_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Expired",
            "last_name": "Guest",
            "email": "expired@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == 409
    assert consume_response.json() == {"detail": "This exception registration offer has expired."}

    audit_entries = (
        await db_session.execute(
            select(ExceptionRegistrationOfferAudit)
            .where(ExceptionRegistrationOfferAudit.offer_id == offer_id)
            .order_by(ExceptionRegistrationOfferAudit.created_at.asc())
        )
    ).scalars().all()
    assert [entry.action for entry in audit_entries] == [
        ExceptionRegistrationOfferAuditAction.ISSUED,
        ExceptionRegistrationOfferAuditAction.EXPIRED,
        ExceptionRegistrationOfferAuditAction.REGISTRATION_REJECTED,
    ]


@pytest.mark.asyncio
async def test_revoked_offer_cannot_be_consumed(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Revoked Offer Use Event",
        prefix="ROU",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "revoked@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = create_response.json()["public_token"]
    offer_id = create_response.json()["id"]
    revoke_response = await client.patch(
        f"/admin/events/{event.id}/exception-offers/{offer_id}/revoke",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={"reason": "No longer needed"},
    )
    assert revoke_response.status_code == 200

    consume_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Revoked",
            "last_name": "Guest",
            "email": "revoked@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == 409
    assert consume_response.json() == {"detail": "This exception registration offer is no longer active."}


@pytest.mark.asyncio
async def test_target_email_mismatch_is_rejected_and_audited(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Mismatch Offer Event",
        prefix="MME",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "correct@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = create_response.json()["public_token"]
    offer_id = create_response.json()["id"]

    consume_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Wrong",
            "last_name": "Guest",
            "email": "wrong@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == 409
    assert consume_response.json() == {
        "detail": "This exception registration offer is not valid for the submitted email address."
    }

    audit_entries = (
        await db_session.execute(
            select(ExceptionRegistrationOfferAudit)
            .where(ExceptionRegistrationOfferAudit.offer_id == offer_id)
            .order_by(ExceptionRegistrationOfferAudit.created_at.asc())
        )
    ).scalars().all()
    assert [entry.action for entry in audit_entries] == [
        ExceptionRegistrationOfferAuditAction.ISSUED,
        ExceptionRegistrationOfferAuditAction.REGISTRATION_ATTEMPTED,
        ExceptionRegistrationOfferAuditAction.REGISTRATION_REJECTED,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing_state",
    [
        RegistrationState.PENDING_PAYMENT,
        RegistrationState.CONFIRMED,
        RegistrationState.WAITLISTED,
    ],
)
async def test_exception_offer_registration_blocks_active_duplicate_states(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    existing_state: RegistrationState,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Exception Duplicate Block Event",
        prefix="EDB",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    await create_registration(
        db_session,
        event=event,
        reg_id=f"EDB-2026-{existing_state.value[:3].upper()}001",
        email="blocked@example.com",
        state=existing_state,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "blocked@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    consume_response = await client.post(
        f"/registrations/exception-offers/{create_response.json()['public_token']}/register",
        json={
            "first_name": "Blocked",
            "last_name": "Guest",
            "email": "blocked@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == 409
    assert consume_response.json() == {
        "detail": "This email has already been used to register for this event."
    }
    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_state", [RegistrationState.FAILED, RegistrationState.CANCELLED])
async def test_exception_offer_registration_allows_failed_or_cancelled_history(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    existing_state: RegistrationState,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Exception Duplicate Allow Event",
        prefix="EDA",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    await create_registration(
        db_session,
        event=event,
        reg_id=f"EDA-2026-{existing_state.value[:3].upper()}001",
        email="allowed@example.com",
        state=existing_state,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "allowed@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    consume_response = await client.post(
        f"/registrations/exception-offers/{create_response.json()['public_token']}/register",
        json={
            "first_name": "Allowed",
            "last_name": "Guest",
            "email": "allowed@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == 201
    assert consume_response.json()["state"] == "confirmed"
    registrations = (await db_session.execute(select(Registration).where(Registration.email == "allowed@example.com"))).scalars().all()
    assert len(registrations) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("refund_status", "expected_status"),
    [
        (RefundRequestStatus.REQUESTED, 409),
        (RefundRequestStatus.COMPLETED, 201),
        (RefundRequestStatus.REJECTED, 201),
    ],
)
async def test_exception_offer_registration_respects_refund_request_status(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    refund_status: RefundRequestStatus,
    expected_status: int,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Exception Refund Status Event",
        prefix="ERS",
        price=5000,
        capacity=5,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    existing_registration = await create_registration(
        db_session,
        event=event,
        reg_id=f"ERS-2026-{refund_status.value[:3].upper()}001",
        email="refundstatus@example.com",
        state=RegistrationState.CANCELLED,
    )
    db_session.add(
        RefundRequest(
            registration_id=existing_registration.id,
            status=refund_status,
            requested_by=RefundRequestedBy.PUBLIC,
            reason="Existing refund workflow",
        )
    )
    await db_session.commit()
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "refundstatus@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    consume_response = await client.post(
        f"/registrations/exception-offers/{create_response.json()['public_token']}/register",
        json={
            "first_name": "Refund",
            "last_name": "Status",
            "email": "refundstatus@example.com",
            "custom_field_values": [],
        },
    )

    assert consume_response.status_code == expected_status
    registrations = (
        await db_session.execute(select(Registration).where(Registration.email == "refundstatus@example.com"))
    ).scalars().all()
    assert len(registrations) == (1 if expected_status == 409 else 2)
    if expected_status == 409:
        assert consume_response.json() == {
            "detail": "This email has already been used to register for this event."
        }
    else:
        assert consume_response.json()["state"] == "confirmed"


@pytest.mark.asyncio
async def test_offer_is_single_use_and_second_consumption_fails_without_duplicate_registration(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Single Use Offer Event",
        prefix="SUE",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )
    create_response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "singleuse@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )
    token = create_response.json()["public_token"]

    first_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Single",
            "last_name": "Use",
            "email": "singleuse@example.com",
            "custom_field_values": [],
        },
    )
    second_response = await client.post(
        f"/registrations/exception-offers/{token}/register",
        json={
            "first_name": "Single",
            "last_name": "Use",
            "email": "singleuse@example.com",
            "custom_field_values": [],
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    registrations = (await db_session.execute(select(Registration))).scalars().all()
    assert len(registrations) == 1


@pytest.mark.asyncio
async def test_free_event_cannot_set_payment_waived_on_offer_creation(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Free Event Offer",
        prefix="FEO",
        price=0,
        capacity=1,
        overflow_rule=OverflowRule.HARD_REJECTION,
    )

    response = await client.post(
        f"/admin/events/{event.id}/exception-offers",
        headers=await auth_headers(client, email="admin@eventapp.local", password="Admin1234!"),
        json={
            "target_email": "freewaive@example.com",
            "payment_waived": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "payment_waived can only be used for paid events."}
