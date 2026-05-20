from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskFailureStatus
from app.models.event import Event
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.payment import Payment
from app.models.registration import Registration
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffEventAccess
from app.models.staff_event_authorization import StaffEventAuthorization
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus
from seed import (
    SEED_EVENT_PREFIXES,
    SEED_LOGIN_PASSWORD,
    SEED_REFERENCE_REG_IDS,
    SEED_STAFF_EMAILS,
    seed_database,
)


EXPECTED_SEED_SUMMARY = {
    "staff_accounts": 6,
    "events": 7,
    "event_field_definitions": 8,
    "batch_registrations": 1,
    "registrations": 23,
    "payments": 15,
    "refund_requests": 3,
    "waitlist_promotion_offers": 3,
    "exception_registration_offers": 4,
    "exception_registration_offer_audits": 8,
    "manual_review_cases": 3,
    "async_task_failures": 3,
    "user_notifications": 4,
    "staff_notifications": 3,
}


async def auth_headers(client, *, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": SEED_LOGIN_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_seed_database_is_idempotent_and_populates_expected_counts(db_session) -> None:
    first_summary = await seed_database(db_session)
    await db_session.commit()

    second_summary = await seed_database(db_session)
    await db_session.commit()

    assert first_summary == EXPECTED_SEED_SUMMARY
    assert second_summary == EXPECTED_SEED_SUMMARY


@pytest.mark.asyncio
async def test_seeded_dataset_preserves_advanced_relationships(db_session) -> None:
    await seed_database(db_session)
    await db_session.commit()

    pending_registration = (
        await db_session.execute(
            select(Registration)
            .where(Registration.reg_id == "TEC-2026-PND001")
            .options(selectinload(Registration.payments))
        )
    ).scalar_one()
    pending_payments = pending_registration.payments
    assert [payment.attempt_number for payment in pending_payments] == [1, 2]
    assert pending_registration.current_payment_id == pending_payments[-1].id
    assert pending_payments[-1].payment_reference == "SEED_TEC_PND001_ATT2"

    override_registration = (
        await db_session.execute(
            select(Registration)
            .where(Registration.reg_id == SEED_REFERENCE_REG_IDS["capacity_override"])
            .options(selectinload(Registration.exception_offer))
        )
    ).scalar_one()
    assert override_registration.current_payment_id is None
    assert override_registration.exception_offer is not None
    assert override_registration.exception_offer.status == ExceptionRegistrationOfferStatus.USED
    assert override_registration.exception_offer.payment_waived is True
    assert override_registration.exception_offer.capacity_override is True

    waitlist_registration = (
        await db_session.execute(
            select(Registration)
            .where(Registration.reg_id == SEED_REFERENCE_REG_IDS["waitlist_manual_review"])
            .options(selectinload(Registration.waitlist_promotion_offer))
        )
    ).scalar_one()
    assert waitlist_registration.waitlist_promotion_offer is not None
    assert waitlist_registration.waitlist_promotion_offer.status == WaitlistPromotionOfferStatus.MANUAL_REVIEW
    assert waitlist_registration.waitlist_promotion_offer.payment_id == waitlist_registration.current_payment_id

    review_staff = (
        await db_session.execute(select(StaffAccount).where(StaffAccount.email == SEED_STAFF_EMAILS["review_staff"]))
    ).scalar_one()
    access_mode = (
        await db_session.execute(select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == review_staff.id))
    ).scalar_one()
    event_access_entries = (
        await db_session.execute(select(StaffEventAccess).where(StaffEventAccess.staff_id == review_staff.id))
    ).scalars().all()
    authorizations = (
        await db_session.execute(
            select(StaffEventAuthorization).where(StaffEventAuthorization.staff_id == review_staff.id)
        )
    ).scalars().all()

    assert access_mode.mode == StaffAccessMode.SELECTED_EVENTS
    assert {entry.event_id for entry in event_access_entries} == {
        (await db_session.execute(select(Event.id).where(Event.prefix == SEED_EVENT_PREFIXES["tech_paid"]))).scalar_one(),
        (await db_session.execute(select(Event.id).where(Event.prefix == SEED_EVENT_PREFIXES["waitlist_forum"]))).scalar_one(),
    }
    assert len(authorizations) == 2
    assert all(authorization.can_manage_manual_reviews for authorization in authorizations)
    assert all(authorization.can_requeue_registrations for authorization in authorizations)


@pytest.mark.asyncio
async def test_seeded_dataset_supports_public_admin_and_staff_surfaces(client, db_session) -> None:
    await seed_database(db_session)
    await db_session.commit()

    community_event = (
        await db_session.execute(select(Event).where(Event.prefix == SEED_EVENT_PREFIXES["community_free"]))
    ).scalar_one()
    full_override_event = (
        await db_session.execute(select(Event).where(Event.prefix == SEED_EVENT_PREFIXES["full_override"]))
    ).scalar_one()
    tech_event = (
        await db_session.execute(select(Event).where(Event.prefix == SEED_EVENT_PREFIXES["tech_paid"]))
    ).scalar_one()

    public_list_response = await client.get("/events")
    public_detail_response = await client.get(f"/events/{community_event.id}")
    assert public_list_response.status_code == 200
    assert public_detail_response.status_code == 200
    assert all("slots_remaining" not in event for event in public_list_response.json()["events"])
    assert "slots_remaining" not in public_detail_response.json()

    admin_analytics_response = await client.get(
        "/admin/analytics",
        headers=await auth_headers(client, email=SEED_STAFF_EMAILS["creator_admin"]),
        params={"event_ids": full_override_event.id},
    )
    assert admin_analytics_response.status_code == 200
    assert admin_analytics_response.json()["capacity"]["capacity_override_count"] == 1

    delegated_offers_response = await client.get(
        f"/admin/events/{full_override_event.id}/exception-offers",
        headers=await auth_headers(client, email=SEED_STAFF_EMAILS["delegated_admin"]),
    )
    assert delegated_offers_response.status_code == 200
    assert delegated_offers_response.json()["total"] == 2

    review_staff_dead_letters_response = await client.get(
        "/staff/dead-letters",
        headers=await auth_headers(client, email=SEED_STAFF_EMAILS["review_staff"]),
        params={"event_id": tech_event.id},
    )
    assert review_staff_dead_letters_response.status_code == 200
    assert review_staff_dead_letters_response.json()["total"] == 1
    assert review_staff_dead_letters_response.json()["failures"][0]["status"] == AsyncTaskFailureStatus.OPEN.value

    selected_staff_dead_letters_response = await client.get(
        "/staff/dead-letters",
        headers=await auth_headers(client, email=SEED_STAFF_EMAILS["selected_staff"]),
        params={"event_id": tech_event.id},
    )
    assert selected_staff_dead_letters_response.status_code == 403

    refund_lookup_response = await client.get(
        "/registrations/lookup",
        params={"reg_id": SEED_REFERENCE_REG_IDS["completed_refund"]},
    )
    history_lookup_response = await client.get(
        "/registrations/lookup",
        params={"reg_id": SEED_REFERENCE_REG_IDS["former_waitlist_history"]},
    )

    assert refund_lookup_response.status_code == 200
    assert refund_lookup_response.json()["refund_request"]["status"] == "completed"
    assert history_lookup_response.status_code == 200
    assert history_lookup_response.json()["registration"]["was_waitlisted"] is True
    assert history_lookup_response.json()["registration"]["previous_waitlist_position"] == 1
    assert history_lookup_response.json()["registration"]["cancellation_reason"] == "overflow_rule_changed"


@pytest.mark.asyncio
async def test_seeded_dead_letters_and_exception_offers_are_queryable(db_session) -> None:
    await seed_database(db_session)
    await db_session.commit()

    failures = (await db_session.execute(select(AsyncTaskFailure))).scalars().all()
    assert {failure.status for failure in failures} == {
        AsyncTaskFailureStatus.OPEN,
        AsyncTaskFailureStatus.ACKNOWLEDGED,
        AsyncTaskFailureStatus.RESOLVED,
    }
    assert all(failure.task_type.value == "email" for failure in failures)
    assert all("api_key" not in (failure.payload_metadata or {}) for failure in failures)

    offers = (
        await db_session.execute(
            select(ExceptionRegistrationOffer).options(selectinload(ExceptionRegistrationOffer.audit_entries))
        )
    ).scalars().all()
    assert len(offers) == 4
    assert sum(len(offer.audit_entries) for offer in offers) == EXPECTED_SEED_SUMMARY["exception_registration_offer_audits"]

    manual_review_waitlist_payment = (
        await db_session.execute(
            select(Payment)
            .join(Registration, Registration.id == Payment.registration_id)
            .where(Registration.reg_id == SEED_REFERENCE_REG_IDS["waitlist_manual_review"])
        )
    ).scalar_one()
    assert manual_review_waitlist_payment.payment_reference == "SEED_WLT_WTL003_ATT1"
