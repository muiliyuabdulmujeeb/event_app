from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.schemas.notification import RegistrationLookupResponse, UserNotificationSeenResponse
from app.services.notification_service import NotificationService


router = APIRouter(tags=["public-lookup"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("/registrations/lookup", response_model=RegistrationLookupResponse)
async def lookup_registration(
    reg_id: Annotated[str, Query(min_length=1)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegistrationLookupResponse:
    service = NotificationService(session=session, settings=settings)
    try:
        return await service.lookup_registration(reg_id.strip())
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch(
    "/registrations/notifications/{notification_id}/seen",
    response_model=UserNotificationSeenResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_registration_notification_seen(
    notification_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> UserNotificationSeenResponse:
    service = NotificationService(session=session, settings=settings)
    try:
        response = await service.mark_user_notification_seen(notification_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
