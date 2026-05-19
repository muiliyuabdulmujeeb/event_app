from __future__ import annotations

import csv
from datetime import datetime
from typing import Any, TextIO

from app.schemas.analytics import AnalyticsRegistrationRowResponse


BASE_DOWNLOAD_COLUMNS = [
    "reg_id",
    "first_name",
    "last_name",
    "email",
    "registration_state",
    "refund_status",
    "cancellation_reason",
    "was_waitlisted",
    "previous_waitlist_position",
    "is_checked_in",
    "checked_in_at",
    "registered_at",
    "is_batch",
    "batch_submitter_name",
    "batch_submitter_email",
    "event_title",
    "event_date",
    "event_location",
    "event_is_free",
    "amount_paid",
    "currency",
    "payment_gateway",
    "payment_reference",
    "paid_at",
    "payment_status",
    "used_exception_offer",
    "payment_waived",
    "capacity_override_applied",
]


def build_download_headers(custom_field_labels: list[str]) -> list[str]:
    return [*BASE_DOWNLOAD_COLUMNS, *custom_field_labels]


def build_download_row(
    registration: AnalyticsRegistrationRowResponse,
    custom_field_labels: list[str],
) -> dict[str, Any]:
    custom_fields = {field.label: field.value for field in registration.custom_fields}
    payment = registration.payment
    row = {
        "reg_id": registration.reg_id,
        "first_name": registration.first_name,
        "last_name": registration.last_name,
        "email": registration.email,
        "registration_state": registration.registration_state.value,
        "refund_status": registration.refund_status.value if registration.refund_status is not None else "",
        "cancellation_reason": (
            registration.cancellation_reason.value if registration.cancellation_reason is not None else ""
        ),
        "was_waitlisted": registration.was_waitlisted,
        "previous_waitlist_position": registration.previous_waitlist_position or "",
        "is_checked_in": registration.is_checked_in,
        "checked_in_at": _format_datetime(registration.checked_in_at),
        "registered_at": _format_datetime(registration.registered_at),
        "is_batch": registration.is_batch,
        "batch_submitter_name": registration.batch_submitter_name or "",
        "batch_submitter_email": registration.batch_submitter_email or "",
        "event_title": registration.event.title,
        "event_date": _format_datetime(registration.event.event_date),
        "event_location": registration.event.location,
        "event_is_free": registration.event.is_free,
        "amount_paid": payment.amount_paid if payment is not None else "",
        "currency": payment.currency if payment is not None else "",
        "payment_gateway": payment.payment_gateway.value if payment and payment.payment_gateway else "",
        "payment_reference": payment.payment_reference if payment is not None else "",
        "paid_at": _format_datetime(payment.paid_at) if payment is not None else "",
        "payment_status": payment.payment_status.value if payment and payment.payment_status else "",
        "used_exception_offer": registration.used_exception_offer,
        "payment_waived": registration.payment_waived,
        "capacity_override_applied": registration.capacity_override_applied,
    }
    for label in custom_field_labels:
        row[label] = custom_fields.get(label, "")
    return row


def write_csv_header(writer: csv.DictWriter, custom_field_labels: list[str]) -> None:
    writer.fieldnames = build_download_headers(custom_field_labels)
    writer.writeheader()


def write_csv_row(writer: csv.DictWriter, registration: AnalyticsRegistrationRowResponse, custom_field_labels: list[str]) -> None:
    writer.writerow(build_download_row(registration, custom_field_labels))


def build_csv_writer(file_obj: TextIO, custom_field_labels: list[str]) -> csv.DictWriter:
    writer = csv.DictWriter(file_obj, fieldnames=build_download_headers(custom_field_labels))
    writer.writeheader()
    return writer


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat().replace("+00:00", "Z")
