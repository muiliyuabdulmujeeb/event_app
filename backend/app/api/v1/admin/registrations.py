from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session, require_admin
from app.core.exceptions import AppError, as_http_exception
from app.models.staff import StaffAccount
from app.models.refund_request import RefundRequestStatus
from app.schemas.refund import (
    AdminRefundRequestListResponse,
    AdminRefundRequestUpdateRequest,
    AdminRefundRequestUpdateResponse,
)
from app.services.email_service import EmailService
from app.services.refund_service import RefundService


router = APIRouter(prefix="/admin/refund-requests", tags=["admin-refund-requests"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=AdminRefundRequestListResponse, status_code=status.HTTP_200_OK)
async def list_refund_requests(
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    status_filter: Annotated[RefundRequestStatus | None, Query(alias="status")] = None,
    event_id: str | None = None,
    reg_id: str | None = None,
) -> AdminRefundRequestListResponse:
    service = RefundService(session=session, settings=settings)
    try:
        return await service.list_refund_requests(status=status_filter, event_id=event_id, reg_id=reg_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/{refund_request_id}", response_model=AdminRefundRequestUpdateResponse, status_code=status.HTTP_200_OK)
async def update_refund_request(
    refund_request_id: str,
    payload: AdminRefundRequestUpdateRequest,
    admin_account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminRefundRequestUpdateResponse:
    service = RefundService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.update_refund_request(
            refund_request_id=refund_request_id,
            payload=payload,
            processed_by=admin_account,
        )
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
