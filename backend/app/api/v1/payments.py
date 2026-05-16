from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.security import utc_now
from app.core.exceptions import (
    AppError,
    InvalidWebhookSignatureError,
    as_http_exception,
)
from app.services.email_service import EmailService
from app.services.payment_processing_service import (
    PAYMENT_FAILED_EVENT,
    PAYMENT_SUCCESS_EVENT,
    PaymentProcessingService,
)
from app.workers.payment_tasks import process_payment_webhook_task


logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.post("/payments/webhook/paystack")
async def paystack_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    _verify_paystack_signature(raw_body=raw_body, signature=signature, secret=settings.paystack_secret_key)

    payload = await request.json()
    event_name = str(payload.get("event", ""))
    normalized_payload = _normalize_paystack_event(payload)
    if normalized_payload is None:
        if event_name == "charge.dispute":
            logger.info("Ignoring Paystack dispute event.")
        return {"status": "ignored"}

    process_payment_webhook_task.delay(normalized_payload)
    return {"status": "accepted"}


@router.post("/payments/webhook/squad")
async def squad_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("x-squad-encrypted-body", "")
    _verify_squad_signature(raw_body=raw_body, signature=signature, secret=settings.squad_secret_key)

    payload = await request.json()
    normalized_payload = _normalize_squad_event(payload)
    if normalized_payload is None:
        return {"status": "ignored"}

    process_payment_webhook_task.delay(normalized_payload)
    return {"status": "accepted"}


@router.post("/mock-payment/confirm/{reference}", status_code=status.HTTP_200_OK)
async def mock_confirm_payment(
    reference: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, str]:
    service = PaymentProcessingService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.process_event(
            event_type=PAYMENT_SUCCESS_EVENT,
            reference=reference,
            paid_at=utc_now(),
        )
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.ticket_email_messages)
        return {"status": "processed"}
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.post("/mock-payment/fail/{reference}", status_code=status.HTTP_200_OK)
async def mock_fail_payment(
    reference: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, str]:
    service = PaymentProcessingService(session=session, settings=settings)
    try:
        await service.process_event(event_type=PAYMENT_FAILED_EVENT, reference=reference)
        await _commit_or_rollback(session)
        return {"status": "processed"}
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


def _verify_paystack_signature(*, raw_body: bytes, signature: str, secret: str) -> None:
    if not secret or not signature:
        raise as_http_exception(InvalidWebhookSignatureError())
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(digest, signature):
        raise as_http_exception(InvalidWebhookSignatureError())


def _verify_squad_signature(*, raw_body: bytes, signature: str, secret: str) -> None:
    if not secret or not signature:
        raise as_http_exception(InvalidWebhookSignatureError())
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest().upper()
    if not hmac.compare_digest(digest, signature):
        raise as_http_exception(InvalidWebhookSignatureError())


def _normalize_paystack_event(payload: dict[str, Any]) -> dict[str, str] | None:
    event_name = str(payload.get("event", ""))
    if event_name != "charge.success":
        return None

    data = payload.get("data") or {}
    reference = str(data.get("reference", "")).strip()
    if not reference:
        return None

    paid_at = data.get("paid_at") or data.get("paidAt")
    normalized_payload = {
        "event_type": PAYMENT_SUCCESS_EVENT,
        "reference": reference,
    }
    if isinstance(paid_at, str) and paid_at.strip():
        normalized_payload["paid_at"] = paid_at
    return normalized_payload


def _normalize_squad_event(payload: dict[str, Any]) -> dict[str, str] | None:
    event_name = str(payload.get("Event", ""))
    body = payload.get("Body") or {}
    transaction_status = str(body.get("transaction_status", "")).strip().lower()
    if event_name != "charge_successful" or transaction_status != "success":
        return None

    reference = str(body.get("transaction_ref") or payload.get("TransactionRef") or "").strip()
    if not reference:
        return None

    paid_at = body.get("created_at")
    normalized_payload = {
        "event_type": PAYMENT_SUCCESS_EVENT,
        "reference": reference,
    }
    if isinstance(paid_at, str) and paid_at.strip():
        normalized_payload["paid_at"] = paid_at
    return normalized_payload
