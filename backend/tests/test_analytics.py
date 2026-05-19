from __future__ import annotations

from datetime import date

import pytest

from app.models.staff import StaffRole
from tests.analytics_helpers import auth_headers, build_analytics_dataset, ensure_staff_account


def _custom_fields_by_label(row: dict) -> dict[str, str]:
    return {field["label"]: field["value"] for field in row["custom_fields"]}


@pytest.mark.asyncio
async def test_admin_analytics_returns_expected_single_event_metrics(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params={"event_ids": dataset.paid_event.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["events"] == [{"id": dataset.paid_event.id, "title": "Paid Analytics Event"}]
    assert body["registration_summary"] == {
        "total_registrations": 10,
        "confirmed": 6,
        "cancelled": 1,
        "waitlisted": 1,
        "refunded": 1,
        "failed": 1,
        "checked_in_count": 1,
        "check_in_rate": "16.67%",
    }
    assert body["revenue"] == {
        "gross_revenue": 30000,
        "net_revenue": 25000,
        "total_refunded": 5000,
        "average_ticket_price": 5000,
        "currency": "NGN",
        "revenue_by_event": [
            {
                "event_id": dataset.paid_event.id,
                "title": "Paid Analytics Event",
                "gross_revenue": 30000,
            }
        ],
    }
    assert body["batch_vs_single"] == {
        "single_registration_count": 6,
        "batch_registration_count": 4,
        "batch_submission_count": 1,
        "average_batch_size": 4.0,
    }
    assert body["capacity"] == {
        "capacity": 10,
        "slots_filled": 7,
        "slots_remaining": 3,
        "waitlist_length": 1,
        "fill_rate": "70.00%",
        "capacity_override_count": 1,
    }
    assert body["registration_trends"]["peak_registration_day"] == "2026-05-06"
    assert len(body["registration_trends"]["daily"]) == 15
    assert body["registration_trends"]["daily"][0] == {
        "date": "2026-05-01",
        "count": 1,
        "cumulative": 1,
    }
    assert body["registration_trends"]["daily"][5] == {
        "date": "2026-05-06",
        "count": 4,
        "cumulative": 9,
    }
    assert body["registration_trends"]["daily"][-1] == {
        "date": "2026-05-15",
        "count": 0,
        "cumulative": 10,
    }


@pytest.mark.asyncio
async def test_admin_analytics_multiple_events_joins_metrics_and_omits_capacity_for_unlimited_scope(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params=[
            ("event_ids", dataset.paid_event.id),
            ("event_ids", dataset.unlimited_event.id),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert [event["title"] for event in body["events"]] == [
        "Paid Analytics Event",
        "Unlimited Analytics Event",
    ]
    assert body["registration_summary"]["total_registrations"] == 11
    assert body["registration_summary"]["confirmed"] == 7
    assert body["revenue"]["gross_revenue"] == 33000
    assert body["revenue"]["net_revenue"] == 28000
    assert body["revenue"]["total_refunded"] == 5000
    assert body["revenue"]["average_ticket_price"] == 4714
    assert body["revenue"]["revenue_by_event"] == [
        {
            "event_id": dataset.paid_event.id,
            "title": "Paid Analytics Event",
            "gross_revenue": 30000,
        },
        {
            "event_id": dataset.unlimited_event.id,
            "title": "Unlimited Analytics Event",
            "gross_revenue": 3000,
        },
    ]
    assert "capacity" not in body


@pytest.mark.asyncio
async def test_registration_table_filters_sorts_and_projects_current_business_fields(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)
    headers = await auth_headers(
        client,
        email=seeded_admin_account.email,
        password="Admin1234!",
    )

    waitlisted_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={"event_ids": dataset.paid_event.id, "state": "waitlisted"},
    )
    assert waitlisted_response.status_code == 200
    waitlisted_body = waitlisted_response.json()
    assert waitlisted_body["total"] == 1
    assert waitlisted_body["registrations"][0]["reg_id"] == dataset.waitlisted_registration_reg_id

    pending_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={"event_ids": dataset.paid_event.id, "payment_status": "pending"},
    )
    assert pending_response.status_code == 200
    pending_body = pending_response.json()
    assert pending_body["total"] == 1
    assert pending_body["registrations"][0]["registration_state"] == "pending_payment"

    batch_day_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={
            "event_ids": dataset.paid_event.id,
            "date_from": date(2026, 5, 6).isoformat(),
            "date_to": date(2026, 5, 6).isoformat(),
        },
    )
    assert batch_day_response.status_code == 200
    batch_day_body = batch_day_response.json()
    assert batch_day_body["total"] == 4
    assert {row["batch_submitter_email"] for row in batch_day_body["registrations"]} == {
        "batch.submitter@example.com"
    }

    custom_field_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={
            "event_ids": dataset.paid_event.id,
            "custom_field": f"{dataset.company_field.id}:VIPCo",
        },
    )
    assert custom_field_response.status_code == 200
    custom_field_body = custom_field_response.json()
    assert custom_field_body["total"] == 1
    waived_row = custom_field_body["registrations"][0]
    assert waived_row["reg_id"] == dataset.waived_registration_reg_id
    assert waived_row["used_exception_offer"] is True
    assert waived_row["payment_waived"] is True
    assert waived_row["capacity_override_applied"] is True
    assert waived_row["payment"] == {
        "amount_paid": 0,
        "currency": "NGN",
        "payment_gateway": None,
        "payment_reference": None,
        "payment_status": None,
        "paid_at": None,
    }

    sorted_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={
            "event_ids": dataset.paid_event.id,
            "sort_by": f"custom_field:{dataset.company_field.id}",
            "sort_order": "asc",
            "page_size": 3,
        },
    )
    assert sorted_response.status_code == 200
    sorted_body = sorted_response.json()
    assert sorted_body["total"] == 10
    assert sorted_body["sort_by"] == f"custom_field:{dataset.company_field.id}"
    assert sorted_body["sort_order"] == "asc"
    assert [
        _custom_fields_by_label(row)["Company"] for row in sorted_body["registrations"]
    ] == ["Acme", "Alpha", "BatchCo A"]

    refunded_row = next(
        row
        for row in sorted_body["registrations"] + custom_field_body["registrations"] + waitlisted_body["registrations"]
        if row["reg_id"] == dataset.refunded_registration_reg_id
    )
    assert refunded_row["refund_status"] == "completed"
    assert refunded_row["cancellation_reason"] is None


@pytest.mark.asyncio
async def test_registration_table_rejects_invalid_custom_field_filter(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics/registrations",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params={"event_ids": dataset.paid_event.id, "custom_field": "bad-format"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "custom_field filters must use the format '<field_definition_id>:<value>'"
    )


@pytest.mark.asyncio
async def test_staff_cannot_access_admin_analytics_endpoints(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)
    staff_account = await ensure_staff_account(
        db_session,
        email="analytics-staff@eventapp.local",
        password="Staff1234!",
        role=StaffRole.STAFF,
    )
    headers = await auth_headers(client, email=staff_account.email, password="Staff1234!")

    analytics_response = await client.get(
        "/admin/analytics",
        headers=headers,
        params={"event_ids": dataset.paid_event.id},
    )
    registrations_response = await client.get(
        "/admin/analytics/registrations",
        headers=headers,
        params={"event_ids": dataset.paid_event.id},
    )

    assert analytics_response.status_code == 403
    assert registrations_response.status_code == 403
