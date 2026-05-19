from __future__ import annotations

import csv
import io

import pytest

from app.models.staff import StaffRole
from tests.analytics_helpers import auth_headers, build_analytics_dataset, ensure_staff_account


@pytest.mark.asyncio
async def test_csv_download_includes_business_columns_and_excludes_internal_fields(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics/download",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params={"format": "csv", "event_ids": dataset.paid_event.id},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="analytics-download.csv"'

    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    assert len(rows) == 10
    assert reader.fieldnames is not None
    assert "reg_id" in reader.fieldnames
    assert "refund_status" in reader.fieldnames
    assert "cancellation_reason" in reader.fieldnames
    assert "was_waitlisted" in reader.fieldnames
    assert "used_exception_offer" in reader.fieldnames
    assert "payment_waived" in reader.fieldnames
    assert "capacity_override_applied" in reader.fieldnames
    assert "Company" in reader.fieldnames
    assert "id" not in reader.fieldnames
    assert "event_id" not in reader.fieldnames
    assert "registration_id" not in reader.fieldnames
    assert "payment_id" not in reader.fieldnames
    assert "batch_id" not in reader.fieldnames
    assert "refund_request_id" not in reader.fieldnames
    assert "manual_review_case_id" not in reader.fieldnames
    assert "current_payment_id" not in reader.fieldnames
    assert "public_token" not in reader.fieldnames
    assert "gateway_checkout_url" not in reader.fieldnames

    refunded_row = next(row for row in rows if row["reg_id"] == dataset.refunded_registration_reg_id)
    assert refunded_row["refund_status"] == "completed"

    waived_row = next(row for row in rows if row["reg_id"] == dataset.waived_registration_reg_id)
    assert waived_row["used_exception_offer"] == "True"
    assert waived_row["payment_waived"] == "True"
    assert waived_row["capacity_override_applied"] == "True"
    assert waived_row["amount_paid"] == "0"
    assert waived_row["payment_status"] == ""


@pytest.mark.asyncio
async def test_csv_download_respects_filters(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics/download",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params={
            "format": "csv",
            "event_ids": dataset.paid_event.id,
            "date_from": "2026-05-06",
            "date_to": "2026-05-06",
        },
    )

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 4
    assert {row["batch_submitter_email"] for row in rows} == {"batch.submitter@example.com"}


@pytest.mark.asyncio
async def test_pdf_download_returns_valid_pdf_with_summary_and_table_content(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)

    response = await client.get(
        "/admin/analytics/download",
        headers=await auth_headers(
            client,
            email=seeded_admin_account.email,
            password="Admin1234!",
        ),
        params={"format": "pdf", "event_ids": dataset.paid_event.id},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="analytics-download.pdf"'
    assert response.content.startswith(b"%PDF")
    assert b"Registration Analytics Export" in response.content
    assert b"Paid Analytics Event" in response.content
    assert dataset.waived_registration_reg_id.encode() in response.content


@pytest.mark.asyncio
async def test_staff_cannot_download_analytics_exports(
    client,
    db_session,
    seeded_admin_account,
) -> None:
    dataset = await build_analytics_dataset(db_session, admin_account=seeded_admin_account)
    staff_account = await ensure_staff_account(
        db_session,
        email="downloads-staff@eventapp.local",
        password="Staff1234!",
        role=StaffRole.STAFF,
    )

    response = await client.get(
        "/admin/analytics/download",
        headers=await auth_headers(client, email=staff_account.email, password="Staff1234!"),
        params={"format": "csv", "event_ids": dataset.paid_event.id},
    )

    assert response.status_code == 403
