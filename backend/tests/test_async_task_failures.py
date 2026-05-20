from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskFailureStatus, AsyncTaskType
from app.models.event import Event, EventState, OverflowRule
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffEventAccess


async def admin_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "admin@eventapp.local", "password": "Admin1234!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def staff_headers(client) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": "staff@eventapp.local", "password": "Staff1234!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
        event_date=datetime(2026, 12, 15, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix=prefix,
        price=5000,
        capacity=20,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.PUBLISHED,
        created_by=created_by.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


async def create_registration_with_payment(
    db_session,
    *,
    event: Event,
    first_name: str,
    email: str,
    reg_id: str,
    payment_reference: str,
) -> tuple[Registration, Payment]:
    registration = Registration(
        event_id=event.id,
        first_name=first_name,
        last_name="Tester",
        email=email,
        reg_id=reg_id,
        state=RegistrationState.FAILED,
    )
    db_session.add(registration)
    await db_session.flush()

    payment = Payment(
        gateway=PaymentGateway.MOCK,
        payment_reference=payment_reference,
        amount=event.price,
        currency="NGN",
        status=PaymentStatus.FAILED,
        attempt_number=1,
        registration_id=registration.id,
    )
    db_session.add(payment)
    await db_session.flush()
    registration.current_payment_id = payment.id
    await db_session.commit()
    await db_session.refresh(registration)
    await db_session.refresh(payment)
    return registration, payment


async def create_dead_letter(
    db_session,
    *,
    task_name: str,
    task_type: AsyncTaskType,
    status: AsyncTaskFailureStatus,
    event: Event | None = None,
    registration: Registration | None = None,
    payment: Payment | None = None,
    failure_category: str = "delivery_failure",
    error_class: str = "RuntimeError",
    error_message: str = "Task failed terminally.",
    attempt_count: int = 4,
) -> AsyncTaskFailure:
    failure = AsyncTaskFailure(
        task_name=task_name,
        task_type=task_type,
        failure_category=failure_category,
        status=status,
        event_id=event.id if event is not None else None,
        registration_id=registration.id if registration is not None else None,
        payment_id=payment.id if payment is not None else None,
        provider_attempts=[
            {"provider": "resend", "attempt": 1, "error_class": error_class, "error_message": error_message}
        ],
        attempt_count=attempt_count,
        error_class=error_class,
        error_message=error_message,
        payload_metadata={"subject": "Failure test"},
        final_failed_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(failure)
    await db_session.commit()
    await db_session.refresh(failure)
    return failure


async def grant_staff_authorization(
    client,
    *,
    event_id: str,
    staff_id: str,
    can_manage_manual_reviews: bool = False,
) -> None:
    response = await client.put(
        f"/admin/events/{event_id}/authorizations/{staff_id}",
        headers=await admin_headers(client),
        json={"can_manage_manual_reviews": can_manage_manual_reviews},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_list_filter_and_get_dead_letter_entries(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event_a = await create_event(db_session, created_by=seeded_admin_account, title="Dead Letter A", prefix="DLA")
    event_b = await create_event(db_session, created_by=seeded_admin_account, title="Dead Letter B", prefix="DLB")
    registration_a, payment_a = await create_registration_with_payment(
        db_session,
        event=event_a,
        first_name="Amina",
        email="amina.deadletter@example.com",
        reg_id="DLA-2026-ABC123",
        payment_reference="DEAD_REF_A1",
    )
    registration_b, payment_b = await create_registration_with_payment(
        db_session,
        event=event_b,
        first_name="Bashir",
        email="bashir.deadletter@example.com",
        reg_id="DLB-2026-DEF456",
        payment_reference="DEAD_REF_B1",
    )
    failure_a = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event_a,
        registration=registration_a,
        payment=payment_a,
        failure_category="email_delivery",
        error_class="EmailDeliveryError",
        error_message="Resend exhausted retries.",
    )
    failure_b = await create_dead_letter(
        db_session,
        task_name="send_notification_task",
        task_type=AsyncTaskType.NOTIFICATION,
        status=AsyncTaskFailureStatus.ACKNOWLEDGED,
        event=event_b,
        registration=registration_b,
        payment=payment_b,
        failure_category="dispatch_failure",
    )
    failure_c = await create_dead_letter(
        db_session,
        task_name="export_task",
        task_type=AsyncTaskType.EXPORT,
        status=AsyncTaskFailureStatus.RESOLVED,
    )

    all_response = await client.get("/staff/dead-letters", headers=await admin_headers(client))
    detail_response = await client.get(
        f"/staff/dead-letters/{failure_c.id}",
        headers=await admin_headers(client),
    )
    event_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"event_id": event_a.id},
    )
    task_type_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"task_type": "notification"},
    )
    status_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"status": "resolved"},
    )
    registration_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"registration_id": registration_b.id},
    )
    payment_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"payment_id": payment_a.id},
    )

    assert all_response.status_code == 200
    assert all_response.json()["total"] == 3
    assert {entry["id"] for entry in all_response.json()["failures"]} == {failure_a.id, failure_b.id, failure_c.id}
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == failure_c.id
    assert detail_response.json()["event_id"] is None
    assert event_filter_response.json()["total"] == 1
    assert event_filter_response.json()["failures"][0]["id"] == failure_a.id
    assert task_type_filter_response.json()["failures"][0]["id"] == failure_b.id
    assert status_filter_response.json()["failures"][0]["id"] == failure_c.id
    assert registration_filter_response.json()["failures"][0]["id"] == failure_b.id
    assert payment_filter_response.json()["failures"][0]["id"] == failure_a.id


@pytest.mark.asyncio
async def test_authorized_staff_can_only_see_event_bound_dead_letters_for_authorized_events(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    accessible_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Accessible Dead Letter Event",
        prefix="ADE",
    )
    blocked_event = await create_event(
        db_session,
        created_by=seeded_admin_account,
        title="Blocked Dead Letter Event",
        prefix="BDE",
    )
    accessible_registration, accessible_payment = await create_registration_with_payment(
        db_session,
        event=accessible_event,
        first_name="Ada",
        email="ada.deadletter@example.com",
        reg_id="ADE-2026-GHI789",
        payment_reference="DEAD_REF_C1",
    )
    blocked_registration, blocked_payment = await create_registration_with_payment(
        db_session,
        event=blocked_event,
        first_name="Bola",
        email="bola.deadletter@example.com",
        reg_id="BDE-2026-JKL012",
        payment_reference="DEAD_REF_D1",
    )
    accessible_failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=accessible_event,
        registration=accessible_registration,
        payment=accessible_payment,
    )
    blocked_failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=blocked_event,
        registration=blocked_registration,
        payment=blocked_payment,
    )
    unbound_failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
    )

    await grant_staff_authorization(
        client,
        event_id=accessible_event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    list_response = await client.get("/staff/dead-letters", headers=await staff_headers(client))
    accessible_detail_response = await client.get(
        f"/staff/dead-letters/{accessible_failure.id}",
        headers=await staff_headers(client),
    )
    blocked_detail_response = await client.get(
        f"/staff/dead-letters/{blocked_failure.id}",
        headers=await staff_headers(client),
    )
    unbound_detail_response = await client.get(
        f"/staff/dead-letters/{unbound_failure.id}",
        headers=await staff_headers(client),
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["failures"][0]["id"] == accessible_failure.id
    assert accessible_detail_response.status_code == 200
    assert blocked_detail_response.status_code == 403
    assert unbound_detail_response.status_code == 403


@pytest.mark.asyncio
async def test_staff_without_manual_review_authorization_cannot_access_dead_letters(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="No Auth Event", prefix="NAE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Chidi",
        email="chidi.deadletter@example.com",
        reg_id="NAE-2026-MNO345",
        payment_reference="DEAD_REF_E1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    list_response = await client.get(
        "/staff/dead-letters",
        headers=await staff_headers(client),
        params={"event_id": event.id},
    )
    detail_response = await client.get(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
    )

    assert list_response.status_code == 403
    assert detail_response.status_code == 403


@pytest.mark.asyncio
async def test_staff_with_authorization_but_without_event_access_cannot_access_dead_letters(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Selected Event", prefix="SEE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Dayo",
        email="dayo.deadletter@example.com",
        reg_id="SEE-2026-PQR678",
        payment_reference="DEAD_REF_F1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    access_mode = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_mode.mode = StaffAccessMode.SELECTED_EVENTS
    await db_session.commit()

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    forbidden_response = await client.get(
        "/staff/dead-letters",
        headers=await staff_headers(client),
        params={"event_id": event.id},
    )
    assert forbidden_response.status_code == 403

    db_session.add(StaffEventAccess(staff_id=seeded_staff_account.id, event_id=event.id))
    await db_session.commit()

    allowed_response = await client.get(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
    )
    assert allowed_response.status_code == 200
    assert allowed_response.json()["id"] == failure.id


@pytest.mark.asyncio
async def test_admin_get_dead_letter_returns_not_found_for_unknown_id(
    client,
    seeded_admin_account: StaffAccount,
) -> None:
    response = await client.get(
        "/staff/dead-letters/atf_missing",
        headers=await admin_headers(client),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_acknowledge_and_resolve_dead_letter_entries(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Lifecycle Event", prefix="LCE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Eniola",
        email="eniola.deadletter@example.com",
        reg_id="LCE-2026-AAA111",
        payment_reference="DEAD_REF_G1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    acknowledge_response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await admin_headers(client),
        json={"status": "acknowledged", "resolution_notes": "Investigating provider outage."},
    )
    resolve_response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await admin_headers(client),
        json={"status": "resolved", "resolution_notes": "Issue closed after provider recovery."},
    )
    detail_response = await client.get(
        f"/staff/dead-letters/{failure.id}",
        headers=await admin_headers(client),
    )

    assert acknowledge_response.status_code == 200
    acknowledged_body = acknowledge_response.json()
    assert acknowledged_body["status"] == "acknowledged"
    assert acknowledged_body["acknowledged_by_staff_id"] == seeded_admin_account.id
    assert acknowledged_body["acknowledged_at"] is not None
    assert acknowledged_body["resolved_by_staff_id"] is None
    assert acknowledged_body["resolution_notes"] == "Investigating provider outage."

    assert resolve_response.status_code == 200
    resolved_body = resolve_response.json()
    assert resolved_body["status"] == "resolved"
    assert resolved_body["acknowledged_by_staff_id"] == seeded_admin_account.id
    assert resolved_body["resolved_by_staff_id"] == seeded_admin_account.id
    assert resolved_body["resolved_at"] is not None
    assert resolved_body["resolution_notes"] == "Issue closed after provider recovery."

    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "resolved"
    assert detail_response.json()["resolved_by_staff_id"] == seeded_admin_account.id


@pytest.mark.asyncio
async def test_admin_can_resolve_open_dead_letter_directly(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Direct Resolve Event", prefix="DRE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Fatima",
        email="fatima.deadletter@example.com",
        reg_id="DRE-2026-BBB222",
        payment_reference="DEAD_REF_H1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await admin_headers(client),
        json={"status": "resolved", "resolution_notes": "Handled without separate acknowledgement."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["acknowledged_by_staff_id"] is None
    assert body["resolved_by_staff_id"] == seeded_admin_account.id
    assert body["resolved_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starting_status", "requested_status"),
    [
        (AsyncTaskFailureStatus.OPEN, "open"),
        (AsyncTaskFailureStatus.ACKNOWLEDGED, "acknowledged"),
        (AsyncTaskFailureStatus.RESOLVED, "acknowledged"),
    ],
)
async def test_invalid_dead_letter_status_transitions_are_rejected(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    starting_status: AsyncTaskFailureStatus,
    requested_status: str,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Invalid Transition Event", prefix="ITE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Ganiyu",
        email="ganiyu.deadletter@example.com",
        reg_id="ITE-2026-CCC333",
        payment_reference="DEAD_REF_I1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=starting_status,
        event=event,
        registration=registration,
        payment=payment,
    )

    response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await admin_headers(client),
        json={"status": requested_status},
    )

    assert response.status_code == 422
    refreshed = await db_session.get(AsyncTaskFailure, failure.id)
    assert refreshed is not None
    assert refreshed.status == starting_status


@pytest.mark.asyncio
async def test_authorized_staff_can_acknowledge_and_resolve_event_bound_dead_letters(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Staff Lifecycle Event", prefix="SLE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Halima",
        email="halima.deadletter@example.com",
        reg_id="SLE-2026-DDD444",
        payment_reference="DEAD_REF_J1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    acknowledge_response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
        json={"status": "acknowledged"},
    )
    resolve_response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
        json={"status": "resolved", "resolution_notes": "Staff closed the issue."},
    )

    assert acknowledge_response.status_code == 200
    assert acknowledge_response.json()["acknowledged_by_staff_id"] == seeded_staff_account.id
    assert resolve_response.status_code == 200
    assert resolve_response.json()["resolved_by_staff_id"] == seeded_staff_account.id
    assert resolve_response.json()["resolution_notes"] == "Staff closed the issue."


@pytest.mark.asyncio
async def test_dead_letter_status_filters_reflect_lifecycle_updates(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Filter Lifecycle Event", prefix="FLE")
    registration_a, payment_a = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Kemi",
        email="kemi.deadletter@example.com",
        reg_id="FLE-2026-GGG777",
        payment_reference="DEAD_REF_M1",
    )
    registration_b, payment_b = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Lekan",
        email="lekan.deadletter@example.com",
        reg_id="FLE-2026-HHH888",
        payment_reference="DEAD_REF_M2",
    )
    acknowledged_failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration_a,
        payment=payment_a,
    )
    resolved_failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration_b,
        payment=payment_b,
    )

    acknowledge_response = await client.patch(
        f"/staff/dead-letters/{acknowledged_failure.id}",
        headers=await admin_headers(client),
        json={"status": "acknowledged", "resolution_notes": "Watching the issue."},
    )
    resolve_response = await client.patch(
        f"/staff/dead-letters/{resolved_failure.id}",
        headers=await admin_headers(client),
        json={"status": "resolved", "resolution_notes": "Delivery issue closed."},
    )
    acknowledged_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"status": "acknowledged"},
    )
    resolved_filter_response = await client.get(
        "/staff/dead-letters",
        headers=await admin_headers(client),
        params={"status": "resolved"},
    )

    assert acknowledge_response.status_code == 200
    assert resolve_response.status_code == 200
    assert acknowledged_filter_response.status_code == 200
    assert resolved_filter_response.status_code == 200
    assert [entry["id"] for entry in acknowledged_filter_response.json()["failures"]] == [acknowledged_failure.id]
    assert acknowledged_filter_response.json()["failures"][0]["resolution_notes"] == "Watching the issue."
    assert [entry["id"] for entry in resolved_filter_response.json()["failures"]] == [resolved_failure.id]
    assert resolved_filter_response.json()["failures"][0]["resolved_by_staff_id"] == seeded_admin_account.id


@pytest.mark.asyncio
async def test_staff_without_manual_review_authorization_cannot_update_dead_letters(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="No Staff Update Auth", prefix="NSU")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Idris",
        email="idris.deadletter@example.com",
        reg_id="NSU-2026-EEE555",
        payment_reference="DEAD_REF_K1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
        json={"status": "acknowledged"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_staff_with_authorization_but_without_event_access_cannot_update_dead_letters(
    client,
    db_session,
    seeded_admin_account: StaffAccount,
    seeded_staff_account: StaffAccount,
) -> None:
    event = await create_event(db_session, created_by=seeded_admin_account, title="Restricted Update Event", prefix="RUE")
    registration, payment = await create_registration_with_payment(
        db_session,
        event=event,
        first_name="Jumoke",
        email="jumoke.deadletter@example.com",
        reg_id="RUE-2026-FFF666",
        payment_reference="DEAD_REF_L1",
    )
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
        event=event,
        registration=registration,
        payment=payment,
    )

    access_mode = (
        await db_session.execute(
            select(StaffAccessModeRecord).where(StaffAccessModeRecord.staff_id == seeded_staff_account.id)
        )
    ).scalar_one()
    access_mode.mode = StaffAccessMode.SELECTED_EVENTS
    await db_session.commit()

    await grant_staff_authorization(
        client,
        event_id=event.id,
        staff_id=seeded_staff_account.id,
        can_manage_manual_reviews=True,
    )

    response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
        json={"status": "acknowledged"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_event_bound_dead_letters_remain_admin_only_for_updates(
    client,
    db_session,
    seeded_staff_account: StaffAccount,
) -> None:
    failure = await create_dead_letter(
        db_session,
        task_name="send_email_task",
        task_type=AsyncTaskType.EMAIL,
        status=AsyncTaskFailureStatus.OPEN,
    )

    response = await client.patch(
        f"/staff/dead-letters/{failure.id}",
        headers=await staff_headers(client),
        json={"status": "acknowledged"},
    )

    assert response.status_code == 403
