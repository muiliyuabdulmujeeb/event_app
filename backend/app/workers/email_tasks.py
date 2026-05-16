from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.exceptions import EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_service import EmailService
from app.workers.tasks import celery_app


@celery_app.task(
    name="app.workers.email_tasks.send_email",
    bind=True,
    autoretry_for=(EmailDeliveryError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_email_task(self, payload: dict) -> dict:  # noqa: ANN001
    return asyncio.run(_send_email(payload))


async def _send_email(payload: dict) -> dict:
    settings = get_settings()
    message = EmailMessage.model_validate(payload)
    result = await EmailService(settings=settings).send_message(message)
    return {
        "provider": result.provider,
        "external_id": result.external_id,
        "to": message.to,
        "subject": message.subject,
    }
