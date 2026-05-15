from __future__ import annotations

import asyncio
from datetime import datetime

from app.core.config import get_settings
from app.db.session import create_engine_from_url, create_session_factory
from app.services.payment_processing_service import PaymentProcessingService
from app.workers.tasks import celery_app


@celery_app.task(name="app.workers.payment_tasks.process_payment_webhook")
def process_payment_webhook_task(payload: dict) -> dict:
    return asyncio.run(_process_payment_webhook(payload))


@celery_app.task(name="app.workers.payment_tasks.expire_stale_payments")
def expire_stale_payments_task() -> list[dict]:
    return asyncio.run(_expire_stale_payments())


async def _process_payment_webhook(payload: dict) -> dict:
    engine = create_engine_from_url(get_settings().database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        try:
            service = PaymentProcessingService(session=session, settings=get_settings())
            result = await service.process_event(
                event_type=str(payload["event_type"]),
                reference=str(payload["reference"]),
                paid_at=_parse_datetime(payload.get("paid_at")),
            )
            await session.commit()
            return {
                "reference": result.reference,
                "event_type": result.event_type,
                "status": result.status.value,
                "processed": result.processed,
                "registration_ids": result.registration_ids,
            }
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


async def _expire_stale_payments() -> list[dict]:
    engine = create_engine_from_url(get_settings().database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        try:
            service = PaymentProcessingService(session=session, settings=get_settings())
            results = await service.expire_stale_payments()
            await session.commit()
            return [
                {
                    "reference": result.reference,
                    "event_type": result.event_type,
                    "status": result.status.value,
                    "processed": result.processed,
                    "registration_ids": result.registration_ids,
                }
                for result in results
            ]
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
