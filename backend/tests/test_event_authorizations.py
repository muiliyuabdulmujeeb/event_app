from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.event import Event, EventState, OverflowRule
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffRole
from app.models.staff_event_authorization import StaffEventAuthorization
from app.schemas.staff import EventAuthorizationUpdateRequest
from app.services.event_authorization_service import EventAuthorizationService


async def admin_headers(client, *, email: str = "admin@eventapp.local", password: str = "Admin1234!") -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def staff_headers(client) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": "staff@eventapp.local", "password": "Staff1234!"})
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
) -> Event:
    event = Event(
        title=title,
        description=f"{title} description",
        event_date=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix=prefix,
        price=1000,
        capacity=100,
        overflow_rule=OverflowRule.WAITLIST,
        state=EventState.PUBLISHED,
        created_by=created_by.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_event_creator_can_list_authorizations(
    client,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    response = await client.get(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations",
        headers=await admin_headers(client),
    )

    assert response.status_code == 200
    assert response.json() == {
        "event_id": seeded_paid_published_event.id,
        "authorizations": [],
    }


@pytest.mark.asyncio
async def test_event_creator_can_grant_valid_admin_permissions(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    delegated_admin = await create_account(
        db_session,
        email="delegate-admin@eventapp.local",
        role=StaffRole.ADMIN,
        password="Delegate1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_admin.id}",
        headers=await admin_headers(client),
        json={
            "can_manage_exception_offers": True,
            "can_change_overflow_rule": True,
            "can_manage_manual_reviews": False,
            "can_requeue_registrations": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == seeded_paid_published_event.id
    assert body["account_id"] == delegated_admin.id
    assert body["role"] == "admin"
    assert body["permissions"] == {
        "can_manage_exception_offers": True,
        "can_change_overflow_rule": True,
        "can_manage_manual_reviews": False,
        "can_requeue_registrations": False,
    }
    assert body["granted_by_staff_id"] == seeded_admin_account.id
    assert body["updated_at"] is not None


@pytest.mark.asyncio
async def test_event_creator_can_grant_valid_staff_permissions(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="delegate-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Delegate1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await admin_headers(client),
        json={
            "can_manage_exception_offers": False,
            "can_change_overflow_rule": False,
            "can_manage_manual_reviews": True,
            "can_requeue_registrations": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "staff"
    assert response.json()["permissions"] == {
        "can_manage_exception_offers": False,
        "can_change_overflow_rule": False,
        "can_manage_manual_reviews": True,
        "can_requeue_registrations": True,
    }


@pytest.mark.asyncio
async def test_non_event_creator_admin_cannot_list_grant_or_revoke_authorizations(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    non_creator_admin = await create_account(
        db_session,
        email="other-admin@eventapp.local",
        role=StaffRole.ADMIN,
        password="OtherAdmin1234!",
    )
    delegated_staff = await create_account(
        db_session,
        email="delegated-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Delegate1234!",
    )

    list_response = await client.get(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations",
        headers=await admin_headers(client, email=non_creator_admin.email, password="OtherAdmin1234!"),
    )
    grant_response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await admin_headers(client, email=non_creator_admin.email, password="OtherAdmin1234!"),
        json={"can_manage_manual_reviews": True},
    )
    revoke_response = await client.delete(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await admin_headers(client, email=non_creator_admin.email, password="OtherAdmin1234!"),
    )

    assert list_response.status_code == 403
    assert grant_response.status_code == 403
    assert revoke_response.status_code == 403
    assert list_response.json() == {"detail": "Only the event creator can manage authorizations for this event."}
    assert grant_response.json() == {"detail": "Only the event creator can manage authorizations for this event."}
    assert revoke_response.json() == {"detail": "Only the event creator can manage authorizations for this event."}


@pytest.mark.asyncio
async def test_staff_cannot_access_event_authorization_routes(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="another-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Another1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await staff_headers(client),
        json={"can_manage_manual_reviews": True},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to perform this action."}


@pytest.mark.asyncio
async def test_invalid_admin_permission_combination_is_rejected(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    delegated_admin = await create_account(
        db_session,
        email="invalid-admin@eventapp.local",
        role=StaffRole.ADMIN,
        password="Invalid1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_admin.id}",
        headers=await admin_headers(client),
        json={
            "can_manage_exception_offers": True,
            "can_manage_manual_reviews": True,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Only exception-offer and overflow permissions can be granted to admin accounts for this event."
    }


@pytest.mark.asyncio
async def test_invalid_staff_permission_combination_is_rejected(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="invalid-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Invalid1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await admin_headers(client),
        json={
            "can_change_overflow_rule": True,
            "can_manage_manual_reviews": True,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Only manual-review and requeue permissions can be granted to staff accounts for this event."
    }


@pytest.mark.asyncio
async def test_creator_cannot_authorize_themselves(
    client,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{seeded_admin_account.id}",
        headers=await admin_headers(client),
        json={"can_manage_exception_offers": True},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "The event creator cannot authorize themselves."}


@pytest.mark.asyncio
async def test_revoke_works_and_revoked_authorization_disappears_from_active_list(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="revoke-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Revoke1234!",
    )
    headers = await admin_headers(client)

    grant_response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=headers,
        json={"can_requeue_registrations": True},
    )
    assert grant_response.status_code == 200

    revoke_response = await client.delete(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=headers,
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json() == {
        "event_id": seeded_paid_published_event.id,
        "account_id": delegated_staff.id,
        "revoked": True,
    }

    authorization = (
        await db_session.execute(
            select(StaffEventAuthorization).where(
                StaffEventAuthorization.event_id == seeded_paid_published_event.id,
                StaffEventAuthorization.staff_id == delegated_staff.id,
            )
        )
    ).scalar_one()
    assert authorization.revoked_by_staff_id == seeded_admin_account.id
    assert authorization.revoked_at is not None
    assert authorization.can_manage_exception_offers is False
    assert authorization.can_change_overflow_rule is False
    assert authorization.can_manage_manual_reviews is False
    assert authorization.can_requeue_registrations is False

    list_response = await client.get(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json() == {
        "event_id": seeded_paid_published_event.id,
        "authorizations": [],
    }


@pytest.mark.asyncio
async def test_upsert_updates_existing_authorization_without_creating_duplicates(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    delegated_admin = await create_account(
        db_session,
        email="upsert-admin@eventapp.local",
        role=StaffRole.ADMIN,
        password="Upsert1234!",
    )
    headers = await admin_headers(client)

    first_response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_admin.id}",
        headers=headers,
        json={"can_manage_exception_offers": True},
    )
    second_response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_admin.id}",
        headers=headers,
        json={"can_change_overflow_rule": True},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["permissions"] == {
        "can_manage_exception_offers": False,
        "can_change_overflow_rule": True,
        "can_manage_manual_reviews": False,
        "can_requeue_registrations": False,
    }

    count = (
        await db_session.execute(
            select(StaffEventAuthorization).where(
                StaffEventAuthorization.event_id == seeded_paid_published_event.id,
                StaffEventAuthorization.staff_id == delegated_admin.id,
            )
        )
    ).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_revoked_authorization_can_be_regranted_cleanly(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="regrant-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Regrant1234!",
    )
    headers = await admin_headers(client)

    await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=headers,
        json={"can_manage_manual_reviews": True},
    )
    await client.delete(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=headers,
    )
    regrant_response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=headers,
        json={"can_requeue_registrations": True},
    )

    assert regrant_response.status_code == 200
    assert regrant_response.json()["permissions"] == {
        "can_manage_exception_offers": False,
        "can_change_overflow_rule": False,
        "can_manage_manual_reviews": False,
        "can_requeue_registrations": True,
    }

    authorization = (
        await db_session.execute(
            select(StaffEventAuthorization).where(
                StaffEventAuthorization.event_id == seeded_paid_published_event.id,
                StaffEventAuthorization.staff_id == delegated_staff.id,
            )
        )
    ).scalar_one()
    assert authorization.revoked_at is None
    assert authorization.revoked_by_staff_id is None


@pytest.mark.asyncio
async def test_authorization_routes_handle_not_found_targets(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    owned_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Owned Event",
        prefix="OWN",
    )
    headers = await admin_headers(client)

    missing_event_response = await client.get(
        "/admin/events/evt_missing/authorizations",
        headers=headers,
    )
    missing_account_response = await client.put(
        f"/admin/events/{owned_event.id}/authorizations/stf_missing",
        headers=headers,
        json={"can_manage_exception_offers": True},
    )
    missing_authorization_response = await client.delete(
        f"/admin/events/{owned_event.id}/authorizations/stf_missing",
        headers=headers,
    )

    assert missing_event_response.status_code == 404
    assert missing_event_response.json() == {"detail": "Event not found."}
    assert missing_account_response.status_code == 404
    assert missing_account_response.json() == {"detail": "Staff account not found."}
    assert missing_authorization_response.status_code == 404
    assert missing_authorization_response.json() == {"detail": "Event authorization not found."}


@pytest.mark.asyncio
async def test_request_with_no_permissions_returns_422_validation_error(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    delegated_staff = await create_account(
        db_session,
        email="empty-staff@eventapp.local",
        role=StaffRole.STAFF,
        password="Empty1234!",
    )

    response = await client.put(
        f"/admin/events/{seeded_paid_published_event.id}/authorizations/{delegated_staff.id}",
        headers=await admin_headers(client),
        json={},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"][0]["loc"] == ["body"]
    assert "At least one delegated permission must be granted." in body["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_event_authorization_service_helpers_work_for_creator_and_delegate(
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    delegated_admin = await create_account(
        db_session,
        email="service-admin@eventapp.local",
        role=StaffRole.ADMIN,
        password="Service1234!",
    )
    event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Service Event",
        prefix="SRV",
    )

    service = EventAuthorizationService(session=db_session)
    response = await service.upsert_event_authorization(
        actor=seeded_admin_account,
        event_id=event.id,
        account_id=delegated_admin.id,
        payload=EventAuthorizationUpdateRequest(can_manage_exception_offers=True),
    )

    assert response.account_id == delegated_admin.id
    assert await service.is_event_creator(actor_id=seeded_admin_account.id, event_id=event.id) is True
    assert await service.is_event_creator(actor_id=delegated_admin.id, event_id=event.id) is False
    assert await service.has_delegated_permission(
        actor_id=delegated_admin.id,
        event_id=event.id,
        permission_name="can_manage_exception_offers",
    ) is True
    assert await service.has_delegated_permission(
        actor_id=delegated_admin.id,
        event_id=event.id,
        permission_name="can_change_overflow_rule",
    ) is False
