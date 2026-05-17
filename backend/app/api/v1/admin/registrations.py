from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session, require_admin
from app.core.exceptions import AppError, as_http_exception
from app.models.staff import StaffAccount
from app.schemas.notification import RegistrationRefundUpdateRequest, RegistrationRefundUpdateResponse
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/admin/registrations", tags=["admin-registrations"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.patch("/{reg_id}/refund", response_model=RegistrationRefundUpdateResponse, status_code=status.HTTP_200_OK)
async def update_registration_refund_state(
    reg_id: str,
    payload: RegistrationRefundUpdateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegistrationRefundUpdateResponse:
    service = NotificationService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.apply_refund_update(reg_id=reg_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages + result.promoted_ticket_email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
