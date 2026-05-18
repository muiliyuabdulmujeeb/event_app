from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, WaitlistPromotionExpiredError, as_http_exception
from app.services.waitlist_promotion_service import WaitlistPromotionService


router = APIRouter(tags=["public-payment-offers"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get(
    "/registrations/payment-offers/{public_token}/initialize",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def initialize_waitlist_payment_offer(
    public_token: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RedirectResponse:
    service = WaitlistPromotionService(session=session, settings=settings)
    try:
        result = await service.initialize_payment_offer(public_token)
        await _commit_or_rollback(session)
        return RedirectResponse(url=result.checkout_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    except WaitlistPromotionExpiredError as exc:
        await _commit_or_rollback(session)
        raise as_http_exception(exc) from exc
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
