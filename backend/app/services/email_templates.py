from __future__ import annotations

from datetime import datetime

from app.core.config import Settings
from app.models.event import Event
from app.models.registration import Registration
from app.schemas.email import EmailMessage


def build_ticket_email_message(
    settings: Settings,
    *,
    event: Event,
    registration: Registration,
) -> EmailMessage:
    event_date = _format_event_datetime(event.event_date)
    full_name = f"{registration.first_name} {registration.last_name}".strip()
    subject = f"Your ticket for {event.title}"
    text_body = "\n".join(
        [
            f"Hello {full_name},",
            "",
            "Your registration has been confirmed. Here are your ticket details:",
            f"Event: {event.title}",
            f"Date: {event_date}",
            f"Location: {event.location}",
            f"Registration ID: {registration.reg_id}",
            "",
            "Please keep this email for your records.",
        ]
    )
    html_body = (
        f"<p>Hello {full_name},</p>"
        "<p>Your registration has been confirmed. Here are your ticket details:</p>"
        "<ul>"
        f"<li><strong>Event:</strong> {event.title}</li>"
        f"<li><strong>Date:</strong> {event_date}</li>"
        f"<li><strong>Location:</strong> {event.location}</li>"
        f"<li><strong>Registration ID:</strong> {registration.reg_id}</li>"
        "</ul>"
        "<p>Please keep this email for your records.</p>"
    )
    return EmailMessage(
        from_email=settings.email_from,
        from_name=settings.email_from_name.strip() or None,
        to=[registration.email],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        metadata={
            "template": "ticket_confirmation",
            "reg_id": registration.reg_id,
            "event_id": event.id,
        },
    )


def build_waitlist_promotion_offer_email_message(
    settings: Settings,
    *,
    event: Event,
    registration: Registration,
    payment_action_url: str,
    offer_expires_at: datetime,
) -> EmailMessage:
    event_date = _format_event_datetime(event.event_date)
    expiry = _format_event_datetime(offer_expires_at)
    full_name = f"{registration.first_name} {registration.last_name}".strip()
    subject = f"Payment link for your spot at {event.title}"
    text_body = "\n".join(
        [
            f"Hello {full_name},",
            "",
            f"A spot has opened for {event.title}.",
            f"Complete payment before {expiry} to secure your registration.",
            f"Event: {event.title}",
            f"Date: {event_date}",
            f"Location: {event.location}",
            f"Registration ID: {registration.reg_id}",
            "",
            f"Pay now: {payment_action_url}",
            "",
            "If payment is not completed before the deadline, the offer will expire automatically.",
        ]
    )
    html_body = (
        f"<p>Hello {full_name},</p>"
        f"<p>A spot has opened for <strong>{event.title}</strong>.</p>"
        f"<p>Complete payment before <strong>{expiry}</strong> to secure your registration.</p>"
        "<ul>"
        f"<li><strong>Event:</strong> {event.title}</li>"
        f"<li><strong>Date:</strong> {event_date}</li>"
        f"<li><strong>Location:</strong> {event.location}</li>"
        f"<li><strong>Registration ID:</strong> {registration.reg_id}</li>"
        "</ul>"
        f"<p><a href=\"{payment_action_url}\">Pay now</a></p>"
        "<p>If payment is not completed before the deadline, the offer will expire automatically.</p>"
    )
    return EmailMessage(
        from_email=settings.email_from,
        from_name=settings.email_from_name.strip() or None,
        to=[registration.email],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        metadata={
            "template": "waitlist_promotion_offer",
            "reg_id": registration.reg_id,
            "event_id": event.id,
        },
    )


def _format_event_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z")
