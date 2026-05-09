from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.event import Event, EventState, OverflowRule
from app.models.registration import Registration, RegistrationState


async def admin_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "email": "admin@eventapp.local",
            "password": "Admin1234!",
        },
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def staff_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "email": "staff@eventapp.local",
            "password": "Staff1234!",
        },
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_admin_can_create_valid_event(client, seeded_admin_account) -> None:
    response = await client.post(
        "/admin/events",
        headers=await admin_headers(client),
        json={
            "title": "Tech Conference 2026",
            "description": "Annual technology conference for developers.",
            "event_date": "2026-08-20T10:00:00Z",
            "location": "Lagos, Nigeria",
            "prefix": "TEC",
            "price": 5000,
            "capacity": 100,
            "overflow_rule": "hard_rejection",
            "custom_fields": [
                {
                    "label": "Phone Number",
                    "field_type": "phone",
                    "is_required": True,
                    "display_order": 1,
                },
                {
                    "label": "T-Shirt Size",
                    "field_type": "text",
                    "is_required": False,
                    "display_order": 2,
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Tech Conference 2026"
    assert body["prefix"] == "TEC"
    assert body["state"] == "draft"
    assert body["is_free"] is False
    assert body["capacity"] == 100
    assert body["overflow_rule"] == "hard_rejection"
    assert len(body["custom_fields"]) == 2
    assert body["registration_counts"]["total_registrations"] == 0


@pytest.mark.asyncio
async def test_invalid_event_prefix_is_rejected(client, seeded_admin_account) -> None:
    response = await client.post(
        "/admin/events",
        headers=await admin_headers(client),
        json={
            "title": "Broken Prefix Event",
            "description": "Invalid prefix test.",
            "event_date": "2026-08-20T10:00:00Z",
            "location": "Lagos, Nigeria",
            "prefix": "tec!",
            "price": 0,
            "capacity": None,
            "overflow_rule": "hard_rejection",
            "custom_fields": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "prefix must be 2-5 uppercase alphanumeric characters"


@pytest.mark.asyncio
async def test_prefix_cannot_be_changed_after_creation(
    client,
    seeded_admin_account,
    seeded_paid_published_event: Event,
) -> None:
    response = await client.patch(
        f"/admin/events/{seeded_paid_published_event.id}",
        headers=await admin_headers(client),
        json={"prefix": "NEW"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Event prefix cannot be changed after creation."}


@pytest.mark.asyncio
async def test_draft_event_is_not_visible_on_public_endpoints(
    client,
    seeded_draft_event: Event,
) -> None:
    list_response = await client.get("/events")
    detail_response = await client.get(f"/events/{seeded_draft_event.id}")

    assert list_response.status_code == 200
    event_ids = {event["id"] for event in list_response.json()["events"]}
    assert seeded_draft_event.id not in event_ids

    assert detail_response.status_code == 404
    assert detail_response.json() == {"detail": "Event not found."}


@pytest.mark.asyncio
async def test_completed_and_cancelled_events_are_not_visible_on_public_endpoints(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    completed_event = Event(
        title="Completed Summit",
        description="Already held.",
        event_date=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        location="Kano, Nigeria",
        prefix="CMP",
        price=1000,
        capacity=20,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.COMPLETED,
        created_by=seeded_admin_account.id,
    )
    cancelled_event = Event(
        title="Cancelled Forum",
        description="Cancelled event.",
        event_date=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        location="Enugu, Nigeria",
        prefix="CAN",
        price=2000,
        capacity=30,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.CANCELLED,
        created_by=seeded_admin_account.id,
    )
    db_session.add_all([completed_event, cancelled_event])
    await db_session.commit()

    list_response = await client.get("/events")
    detail_completed_response = await client.get(f"/events/{completed_event.id}")
    detail_cancelled_response = await client.get(f"/events/{cancelled_event.id}")

    assert list_response.status_code == 200
    event_ids = {event["id"] for event in list_response.json()["events"]}
    assert completed_event.id not in event_ids
    assert cancelled_event.id not in event_ids
    assert detail_completed_response.status_code == 404
    assert detail_cancelled_response.status_code == 404


@pytest.mark.asyncio
async def test_published_event_is_visible_on_public_endpoints(
    client,
    seeded_paid_published_event: Event,
) -> None:
    list_response = await client.get("/events")
    detail_response = await client.get(f"/events/{seeded_paid_published_event.id}")

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["events"][0]["id"] == seeded_paid_published_event.id

    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == seeded_paid_published_event.id
    assert detail_body["state"] == "published"
    assert len(detail_body["custom_fields"]) == 2


@pytest.mark.asyncio
async def test_invalid_state_transition_is_rejected(
    client,
    seeded_admin_account,
    seeded_paid_published_event: Event,
) -> None:
    response = await client.patch(
        f"/admin/events/{seeded_paid_published_event.id}/state",
        headers=await admin_headers(client),
        json={"state": "draft"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid event state transition from 'published' to 'draft'."
    }


@pytest.mark.asyncio
async def test_valid_state_transition_updates_event(
    client,
    seeded_admin_account,
    seeded_draft_event: Event,
) -> None:
    response = await client.patch(
        f"/admin/events/{seeded_draft_event.id}/state",
        headers=await admin_headers(client),
        json={"state": "published"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "published"


@pytest.mark.asyncio
async def test_admin_event_list_returns_all_states(
    client,
    db_session,
    seeded_admin_account,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
    seeded_draft_event: Event,
) -> None:
    completed_event = Event(
        title="Completed Summit",
        description="Already held.",
        event_date=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        location="Kano, Nigeria",
        prefix="CMP",
        price=1000,
        capacity=20,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.COMPLETED,
        created_by=seeded_admin_account.id,
    )
    cancelled_event = Event(
        title="Cancelled Forum",
        description="Cancelled event.",
        event_date=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        location="Enugu, Nigeria",
        prefix="CAN",
        price=2000,
        capacity=30,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.CANCELLED,
        created_by=seeded_admin_account.id,
    )
    db_session.add_all([completed_event, cancelled_event])
    await db_session.commit()

    response = await client.get("/admin/events", headers=await admin_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    states = {event["state"] for event in body["events"]}
    assert states == {"draft", "published", "completed", "cancelled"}


@pytest.mark.asyncio
async def test_public_event_list_supports_search_and_is_free_filters(
    client,
    seeded_free_published_event: Event,
    seeded_paid_published_event: Event,
    seeded_draft_event: Event,
) -> None:
    free_response = await client.get("/events", params={"is_free": "true"})
    paid_response = await client.get("/events", params={"is_free": "false"})
    search_response = await client.get("/events", params={"search": "Conference"})

    assert free_response.status_code == 200
    assert free_response.json()["total"] == 1
    assert free_response.json()["events"][0]["id"] == seeded_free_published_event.id

    assert paid_response.status_code == 200
    assert paid_response.json()["total"] == 1
    assert paid_response.json()["events"][0]["id"] == seeded_paid_published_event.id

    assert search_response.status_code == 200
    assert search_response.json()["total"] == 1
    assert search_response.json()["events"][0]["title"] == "Tech Conference 2026"


@pytest.mark.asyncio
async def test_admin_event_detail_includes_registration_counts(
    client,
    db_session,
    seeded_paid_published_event: Event,
) -> None:
    registrations = [
        Registration(
            event_id=seeded_paid_published_event.id,
            first_name="Amina",
            last_name="Bello",
            email="amina@example.com",
            reg_id="TEC-2026-ABC123",
            state=RegistrationState.CONFIRMED,
        ),
        Registration(
            event_id=seeded_paid_published_event.id,
            first_name="Chidi",
            last_name="Okonkwo",
            email="chidi@example.com",
            reg_id="TEC-2026-DEF456",
            state=RegistrationState.CANCELLED,
        ),
        Registration(
            event_id=seeded_paid_published_event.id,
            first_name="Ngozi",
            last_name="Eze",
            email="ngozi@example.com",
            reg_id="TEC-2026-GHI789",
            state=RegistrationState.WAITLISTED,
            waitlist_position=1,
        ),
    ]
    db_session.add_all(registrations)
    await db_session.commit()

    response = await client.get(
        f"/admin/events/{seeded_paid_published_event.id}",
        headers=await admin_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == seeded_paid_published_event.id
    assert body["registration_counts"]["total_registrations"] == 3
    assert body["registration_counts"]["confirmed"] == 1
    assert body["registration_counts"]["cancelled"] == 1
    assert body["registration_counts"]["waitlisted"] == 1
    assert body["slots_remaining"] == 99


@pytest.mark.asyncio
async def test_staff_cannot_access_admin_event_routes(
    client,
    seeded_staff_account,
) -> None:
    response = await client.get("/admin/events", headers=await staff_headers(client))

    assert response.status_code == 403
