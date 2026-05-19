from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.event import Event, EventFieldDefinition
from app.models.notification import StaffNotification
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import Registration, RegistrationFieldValue, RegistrationState
from app.models.staff import StaffAccessModeRecord, StaffAccount, StaffEventAccess


async def admin_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "admin@eventapp.local", "password": "Admin1234!"},
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def staff_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "staff@eventapp.local", "password": "Staff1234!"},
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def create_registration(
    db_session,
    *,
    event: Event,
    email: str,
    reg_id: str,
    state: RegistrationState = RegistrationState.CONFIRMED,
    is_checked_in: bool = False,
    checked_in_at: datetime | None = None,
    custom_field_values: list[tuple[EventFieldDefinition, str]] | None = None,
    with_successful_payment: bool = False,
) -> Registration:
    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Bello",
        email=email,
        reg_id=reg_id,
        state=state,
        is_checked_in=is_checked_in,
        checked_in_at=checked_in_at,
    )
    db_session.add(registration)
    await db_session.flush()

    for field_definition, value in custom_field_values or []:
        db_session.add(
            RegistrationFieldValue(
                registration_id=registration.id,
                field_definition_id=field_definition.id,
                value=value,
            )
        )

    if with_successful_payment:
        payment = Payment(
            gateway=PaymentGateway.MOCK,
            payment_reference=f"MOCK_{reg_id.replace('-', '')}",
            amount=event.price,
            currency="NGN",
            status=PaymentStatus.SUCCESSFUL,
            registration_id=registration.id,
            attempt_number=1,
            paid_at=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        )
        db_session.add(payment)
        await db_session.flush()
        registration.current_payment_id = payment.id

    await db_session.commit()
    await db_session.refresh(registration)
    return registration


@pytest.mark.asyncio
async def test_staff_can_search_by_reg_id(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    phone_field, shirt_field = seeded_paid_published_event.field_definitions
    registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="amina.bello@example.com",
        reg_id="TEC-2026-ABC123",
        custom_field_values=[
            (phone_field, "+2348012345678"),
            (shirt_field, "L"),
        ],
        with_successful_payment=True,
    )

    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"reg_id": registration.reg_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["registrations"][0] == {
        "reg_id": "TEC-2026-ABC123",
        "first_name": "Amina",
        "last_name": "Bello",
        "email": "amina.bello@example.com",
        "state": "confirmed",
        "is_checked_in": False,
        "checked_in_at": None,
        "registered_at": body["registrations"][0]["registered_at"],
        "is_batch": False,
        "custom_field_values": [
            {"label": "Phone Number", "value": "+2348012345678"},
            {"label": "T-Shirt Size", "value": "L"},
        ],
            "event": {
                "id": seeded_paid_published_event.id,
                "title": "Tech Conference 2026",
                "event_date": "2026-08-20T10:00:00Z",
                "location": "Lagos, Nigeria",
                "is_free": False,
                "state": "published",
                "capacity_override_count": 0,
            },
        "payment": {
            "status": "successful",
            "amount_paid": 5000,
            "currency": "NGN",
            "paid_at": "2026-05-16T12:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_staff_can_search_by_email(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
) -> None:
    await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="shared@example.com",
        reg_id="CMT-2026-ABC123",
    )
    await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="shared@example.com",
        reg_id="TEC-2026-ABC123",
        with_successful_payment=True,
    )

    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"email": "shared@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {registration["reg_id"] for registration in body["registrations"]} == {
        "CMT-2026-ABC123",
        "TEC-2026-ABC123",
    }


@pytest.mark.asyncio
async def test_admin_can_use_staff_registration_search_endpoint(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="admin-search@example.com",
        reg_id="CMT-2026-XYZ789",
    )

    response = await client.get(
        "/staff/registrations",
        headers=await admin_headers(client),
        params={"reg_id": registration.reg_id},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["registrations"][0]["reg_id"] == "CMT-2026-XYZ789"


@pytest.mark.asyncio
async def test_selected_events_staff_cannot_access_unauthorized_reg_id(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
) -> None:
    access_record = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_record.mode = "selected_events"
    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=seeded_free_published_event.id))
    await db_session.commit()

    registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="unauthorized@example.com",
        reg_id="TEC-2026-UNAUTH",
    )

    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"reg_id": registration.reg_id},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have access to registrations for this event."}


@pytest.mark.asyncio
async def test_selected_events_email_query_returns_only_authorized_results(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
) -> None:
    access_record = (await db_session.execute(select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id))).scalar_one()
    access_record.mode = "selected_events"
    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=seeded_free_published_event.id))
    await db_session.commit()

    await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="partial@example.com",
        reg_id="CMT-2026-AUTH01",
    )
    await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="partial@example.com",
        reg_id="TEC-2026-AUTH02",
    )

    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"email": "partial@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["registrations"][0]["reg_id"] == "CMT-2026-AUTH01"


@pytest.mark.asyncio
async def test_selected_events_email_query_with_only_unauthorized_matches_returns_403(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
) -> None:
    access_record = (await db_session.execute(select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id))).scalar_one()
    access_record.mode = "selected_events"
    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=seeded_free_published_event.id))
    await db_session.commit()

    await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="blocked@example.com",
        reg_id="TEC-2026-BLOCK1",
    )

    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"email": "blocked@example.com"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have access to registrations for this event."}


@pytest.mark.asyncio
async def test_checkin_sets_is_checked_in_and_checked_in_at(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="checkin@example.com",
        reg_id="CMT-2026-CHECK1",
    )

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/checkin",
        headers=await staff_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reg_id"] == "CMT-2026-CHECK1"
    assert body["state"] == "confirmed"
    assert body["is_checked_in"] is True
    assert body["checked_in_at"] is not None

    await db_session.refresh(registration)
    assert registration.is_checked_in is True
    assert registration.checked_in_at is not None


@pytest.mark.asyncio
async def test_uncheckin_clears_checked_in_fields(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="uncheck@example.com",
        reg_id="CMT-2026-UNC001",
        is_checked_in=True,
        checked_in_at=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
    )

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/uncheckin",
        headers=await staff_headers(client),
    )

    assert response.status_code == 200
    assert response.json() == {
        "reg_id": "CMT-2026-UNC001",
        "state": "confirmed",
        "is_checked_in": False,
        "checked_in_at": None,
    }

    await db_session.refresh(registration)
    assert registration.is_checked_in is False
    assert registration.checked_in_at is None


@pytest.mark.asyncio
async def test_checkin_non_confirmed_registration_returns_409(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_paid_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_paid_published_event,
        email="pending@example.com",
        reg_id="TEC-2026-PEND01",
        state=RegistrationState.PENDING_PAYMENT,
    )

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/checkin",
        headers=await staff_headers(client),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only confirmed registrations can be checked in."}


@pytest.mark.asyncio
async def test_checkin_already_checked_in_registration_returns_409(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="already@example.com",
        reg_id="CMT-2026-ALRDY1",
        is_checked_in=True,
        checked_in_at=datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc),
    )

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/checkin",
        headers=await staff_headers(client),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This registration has already been checked in."}


@pytest.mark.asyncio
async def test_uncheckin_without_existing_checkin_returns_409(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    registration = await create_registration(
        db_session,
        event=seeded_free_published_event,
        email="notchecked@example.com",
        reg_id="CMT-2026-NOCHK1",
    )

    response = await client.patch(
        f"/staff/registrations/{registration.reg_id}/uncheckin",
        headers=await staff_headers(client),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This registration is not currently checked in."}


@pytest.mark.asyncio
async def test_registration_search_requires_exactly_one_query_parameter(
    client,
    seeded_staff_account: StaffAccount,
) -> None:
    none_response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
    )
    both_response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"reg_id": "TEC-2026-ABC123", "email": "amina@example.com"},
    )

    assert none_response.status_code == 422
    assert none_response.json() == {"detail": "Provide exactly one of reg_id or email."}
    assert both_response.status_code == 422
    assert both_response.json() == {"detail": "Provide exactly one of reg_id or email."}


@pytest.mark.asyncio
async def test_reg_id_search_not_found_returns_404(
    client,
    seeded_staff_account: StaffAccount,
) -> None:
    response = await client.get(
        "/staff/registrations",
        headers=await staff_headers(client),
        params={"reg_id": "TEC-2026-NOTFND"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "No registration found for the provided reg_id."}


@pytest.mark.asyncio
async def test_staff_notifications_list_unread_and_mark_read(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
) -> None:
    unread = StaffNotification(
        staff_id=seeded_staff_account.id,
        title="Access updated",
        body="You have been granted access to Tech Conference 2026.",
        is_read=False,
    )
    already_read = StaffNotification(
        staff_id=seeded_staff_account.id,
        title="Old notice",
        body="Already read.",
        is_read=True,
    )
    db_session.add_all([unread, already_read])
    await db_session.commit()

    list_response = await client.get(
        "/staff/notifications",
        headers=await staff_headers(client),
    )

    assert list_response.status_code == 200
    assert list_response.json() == {
        "notifications": [
            {
                "id": unread.id,
                "title": "Access updated",
                "body": "You have been granted access to Tech Conference 2026.",
                "is_read": False,
                "created_at": list_response.json()["notifications"][0]["created_at"],
            }
        ],
        "total": 1,
    }

    mark_response = await client.patch(
        f"/staff/notifications/{unread.id}/read",
        headers=await staff_headers(client),
    )
    assert mark_response.status_code == 200
    assert mark_response.json() == {"id": unread.id, "is_read": True}

    second_list_response = await client.get(
        "/staff/notifications",
        headers=await staff_headers(client),
    )
    assert second_list_response.status_code == 200
    assert second_list_response.json() == {"notifications": [], "total": 0}


@pytest.mark.asyncio
async def test_staff_cannot_mark_another_accounts_notification_read(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
    seeded_admin_account: StaffAccount,
) -> None:
    notification = StaffNotification(
        staff_id=seeded_admin_account.id,
        title="Admin notice",
        body="Only admin should see this.",
        is_read=False,
    )
    db_session.add(notification)
    await db_session.commit()

    response = await client.patch(
        f"/staff/notifications/{notification.id}/read",
        headers=await staff_headers(client),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Staff notification not found."}


@pytest.mark.asyncio
async def test_admin_can_toggle_staff_account_active_state_and_login_reflects_change(
    client,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    response = await client.patch(
        f"/admin/staff/{seeded_staff_account.id}",
        headers=await admin_headers(client),
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    login_response = await client.post(
        "/auth/login",
        json={"email": "staff@eventapp.local", "password": "Staff1234!"},
    )

    assert login_response.status_code == 403
    assert login_response.json() == {"detail": "This account has been disabled."}


@pytest.mark.asyncio
async def test_admin_can_set_selected_events_mode_and_manage_event_access(
    client,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
) -> None:
    headers = await admin_headers(client)

    mode_response = await client.put(
        f"/admin/staff/{seeded_staff_account.id}/access",
        headers=headers,
        json={"mode": "selected_events"},
    )
    assert mode_response.status_code == 200
    assert mode_response.json() == {
        "staff_id": seeded_staff_account.id,
        "access_mode": "selected_events",
        "selected_events": [],
    }

    add_first = await client.post(
        f"/admin/staff/{seeded_staff_account.id}/access/events",
        headers=headers,
        json={"event_id": seeded_free_published_event.id},
    )
    add_second = await client.post(
        f"/admin/staff/{seeded_staff_account.id}/access/events",
        headers=headers,
        json={"event_id": seeded_paid_published_event.id},
    )
    assert add_first.status_code == 200
    assert add_second.status_code == 200
    assert {event["id"] for event in add_second.json()["selected_events"]} == {
        seeded_free_published_event.id,
        seeded_paid_published_event.id,
    }

    detail_response = await client.get(
        f"/admin/staff/{seeded_staff_account.id}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["access_mode"] == "selected_events"
    assert {event["id"] for event in detail_response.json()["selected_events"]} == {
        seeded_free_published_event.id,
        seeded_paid_published_event.id,
    }

    remove_response = await client.delete(
        f"/admin/staff/{seeded_staff_account.id}/access/events/{seeded_paid_published_event.id}",
        headers=headers,
    )
    assert remove_response.status_code == 200
    assert remove_response.json()["selected_events"] == [
        {"id": seeded_free_published_event.id, "title": "Community Meetup 2026"}
    ]

    all_events_response = await client.put(
        f"/admin/staff/{seeded_staff_account.id}/access",
        headers=headers,
        json={"mode": "all_events"},
    )
    assert all_events_response.status_code == 200
    assert all_events_response.json() == {
        "staff_id": seeded_staff_account.id,
        "access_mode": "all_events",
        "selected_events": [],
    }


@pytest.mark.asyncio
async def test_adding_event_access_requires_selected_events_mode(
    client,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    response = await client.post(
        f"/admin/staff/{seeded_staff_account.id}/access/events",
        headers=await admin_headers(client),
        json={"event_id": seeded_free_published_event.id},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Event-specific access can only be modified when access mode is selected_events."
    }


@pytest.mark.asyncio
async def test_adding_duplicate_event_access_returns_409(
    client,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    headers = await admin_headers(client)
    await client.put(
        f"/admin/staff/{seeded_staff_account.id}/access",
        headers=headers,
        json={"mode": "selected_events"},
    )
    await client.post(
        f"/admin/staff/{seeded_staff_account.id}/access/events",
        headers=headers,
        json={"event_id": seeded_free_published_event.id},
    )

    response = await client.post(
        f"/admin/staff/{seeded_staff_account.id}/access/events",
        headers=headers,
        json={"event_id": seeded_free_published_event.id},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This event is already in the staff access list."}


@pytest.mark.asyncio
async def test_removing_missing_selected_event_access_returns_422(
    client,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
    seeded_free_published_event: Event,
) -> None:
    headers = await admin_headers(client)
    await client.put(
        f"/admin/staff/{seeded_staff_account.id}/access",
        headers=headers,
        json={"mode": "selected_events"},
    )

    response = await client.delete(
        f"/admin/staff/{seeded_staff_account.id}/access/events/{seeded_free_published_event.id}",
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "This event is not currently in the staff access list."}
