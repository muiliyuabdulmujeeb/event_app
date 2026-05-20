from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.config import get_settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.core.security import utc_now
from app.db.session import create_engine_from_url, create_session_factory
from app.models.async_task_failure import AsyncTaskType
from app.schemas.email import EmailMessage
from app.services.async_task_failure_service import AsyncTaskFailureService
from app.services.email_service import EmailService
from app.workers.tasks import celery_app


@dataclass(frozen=True)
class EmailRetryRequired(Exception):
    payload: dict[str, Any]
    countdown: int
    max_retries: int


@celery_app.task(
    name="app.workers.email_tasks.send_email",
    bind=True,
)
def send_email_task(self, payload: dict) -> dict:  # noqa: ANN001
    try:
        return asyncio.run(_send_email(payload, retry_count=self.request.retries))
    except EmailRetryRequired as exc:
        raise self.retry(
            kwargs={"payload": exc.payload},
            countdown=exc.countdown,
            max_retries=exc.max_retries,
        )


async def _send_email(payload: dict, *, retry_count: int = 0) -> dict:
    settings = get_settings()
    provider_attempts = _extract_provider_attempts(payload)

    try:
        message = EmailMessage.model_validate(payload)
    except PydanticValidationError as exc:
        await _record_terminal_failure(
            settings=settings,
            payload=payload,
            provider_attempts=provider_attempts,
            attempt_count=max(1, retry_count + 1),
            failure_category="message_validation",
            error_class=type(exc).__name__,
            error_message=str(exc),
        )
        raise EmailDeliveryError("Email payload validation failed.") from exc

    try:
        result = await EmailService(settings=settings).send_message(
            message,
            previous_attempts=provider_attempts,
        )
    except EmailConfigurationError as exc:
        await _record_terminal_failure(
            settings=settings,
            payload=payload,
            provider_attempts=provider_attempts,
            attempt_count=max(1, len(provider_attempts) or retry_count + 1),
            failure_category="configuration_failure",
            error_class=type(exc).__name__,
            error_message=str(exc),
        )
        raise EmailDeliveryError(str(exc)) from exc
    if result.success:
        assert result.send_result is not None
        return {
            "provider": result.send_result.provider,
            "external_id": result.send_result.external_id,
            "to": message.to,
            "subject": message.subject,
            "provider_attempts": result.provider_attempts,
        }

    next_payload = dict(payload)
    next_payload["_provider_attempts"] = result.provider_attempts
    if result.should_retry:
        raise EmailRetryRequired(
            payload=next_payload,
            countdown=_retry_backoff_seconds(retry_count),
            max_retries=result.total_allowed_attempts - 1,
        )

    await _record_terminal_failure(
        settings=settings,
        payload=next_payload,
        provider_attempts=result.provider_attempts,
        attempt_count=len(result.provider_attempts) or max(1, retry_count + 1),
        failure_category=result.failure_category or "delivery_failure",
        error_class=result.error_class or "EmailDeliveryError",
        error_message=result.error_message or "Email delivery failed.",
    )
    raise EmailDeliveryError(result.error_message or "Email delivery failed.")


async def _record_terminal_failure(
    *,
    settings,
    payload: dict[str, Any],
    provider_attempts: list[dict[str, Any]],
    attempt_count: int,
    failure_category: str,
    error_class: str,
    error_message: str,
) -> None:
    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        try:
            service = AsyncTaskFailureService(session=session)
            metadata = payload.get("metadata") or {}
            await service.create_failure(
                task_name="app.workers.email_tasks.send_email",
                task_type=AsyncTaskType.EMAIL,
                failure_category=failure_category,
                error_class=error_class,
                error_message=error_message,
                provider_attempts=provider_attempts,
                attempt_count=max(1, attempt_count),
                payload_metadata=_sanitize_payload_metadata(payload),
                final_failed_at=utc_now(),
                event_id=_coerce_optional_str(metadata.get("event_id")),
                registration_id=_coerce_optional_str(metadata.get("registration_id")),
                reg_id=_coerce_optional_str(metadata.get("reg_id")),
                payment_id=_coerce_optional_str(metadata.get("payment_id")),
                payment_reference=_coerce_optional_str(metadata.get("payment_reference")),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def _extract_provider_attempts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_attempts = payload.get("_provider_attempts")
    if not isinstance(raw_attempts, list):
        return []
    attempts: list[dict[str, Any]] = []
    for raw_attempt in raw_attempts:
        if isinstance(raw_attempt, dict):
            attempts.append(dict(raw_attempt))
    return attempts


def _sanitize_payload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_email": payload.get("from_email"),
        "from_name": payload.get("from_name"),
        "to": payload.get("to") or [],
        "cc": payload.get("cc") or [],
        "bcc": payload.get("bcc") or [],
        "reply_to": payload.get("reply_to"),
        "subject": payload.get("subject"),
        "metadata": payload.get("metadata") or {},
    }


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _retry_backoff_seconds(retry_count: int) -> int:
    return 2 ** retry_count
