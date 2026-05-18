from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db.session import create_engine_from_url, create_session_factory
from app.services.waitlist_promotion_service import WaitlistPromotionService
from app.workers.tasks import celery_app


@celery_app.task(name="app.workers.waitlist_promotion_tasks.expire_stale_waitlist_promotion_offers")
def expire_stale_waitlist_promotion_offers_task() -> list[dict]:
    return asyncio.run(_expire_stale_waitlist_promotion_offers())


async def _expire_stale_waitlist_promotion_offers() -> list[dict]:
    engine = create_engine_from_url(get_settings().database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        try:
            service = WaitlistPromotionService(session=session, settings=get_settings())
            results = await service.expire_stale_promotion_offers()
            await session.commit()
            return [
                {
                    "public_token": result.public_token,
                    "reg_id": result.reg_id,
                    "status": result.status.value,
                }
                for result in results
            ]
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()
