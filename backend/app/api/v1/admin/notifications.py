from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session, require_admin
from app.core.exceptions import AppError, as_http_exception
from app.models.staff import StaffAccount
from app.schemas.notification import AdminNotificationCreateRequest, AdminNotificationDispatchResponse
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.post("", response_model=AdminNotificationDispatchResponse, status_code=status.HTTP_200_OK)
async def send_admin_notification(
    payload: AdminNotificationCreateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminNotificationDispatchResponse:
    service = NotificationService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.dispatch_admin_notification(payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
