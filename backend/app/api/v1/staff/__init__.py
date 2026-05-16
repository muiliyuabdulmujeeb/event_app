from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_account, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.models.staff import StaffAccount
from app.schemas.staff import (
    StaffCheckInResponse,
    StaffNotificationListResponse,
    StaffNotificationReadResponse,
    StaffRegistrationSearchResponse,
)
from app.services.staff_service import StaffService


router = APIRouter(prefix="/staff", tags=["staff"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("/registrations", response_model=StaffRegistrationSearchResponse)
async def search_registrations(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    reg_id: Annotated[str | None, Query()] = None,
    email: Annotated[str | None, Query()] = None,
) -> StaffRegistrationSearchResponse:
    service = StaffService(session=session)
    try:
        return await service.search_registrations(actor=account, reg_id=reg_id, email=email)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/checkin", response_model=StaffCheckInResponse, status_code=status.HTTP_200_OK)
async def check_in_registration(
    reg_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffCheckInResponse:
    service = StaffService(session=session)
    try:
        response = await service.check_in_registration(actor=account, reg_id=reg_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/uncheckin", response_model=StaffCheckInResponse, status_code=status.HTTP_200_OK)
async def uncheck_in_registration(
    reg_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffCheckInResponse:
    service = StaffService(session=session)
    try:
        response = await service.uncheck_in_registration(actor=account, reg_id=reg_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.get("/notifications", response_model=StaffNotificationListResponse)
async def list_staff_notifications(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffNotificationListResponse:
    service = StaffService(session=session)
    try:
        return await service.list_unread_notifications(actor=account)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/notifications/{notification_id}/read", response_model=StaffNotificationReadResponse, status_code=status.HTTP_200_OK)
async def mark_staff_notification_read(
    notification_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffNotificationReadResponse:
    service = StaffService(session=session)
    try:
        response = await service.mark_notification_read(actor=account, notification_id=notification_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
