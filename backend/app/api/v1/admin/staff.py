from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, require_admin
from app.core.exceptions import AppError, as_http_exception
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import (
    StaffAccessConfigResponse,
    StaffAccountDetailResponse,
    StaffAccountSummary,
    StaffAccountUpdateRequest,
    StaffEventAccessAddRequest,
    StaffAccessModeUpdateRequest,
)
from app.services.staff_service import StaffService

router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=list[StaffAccountSummary])
async def list_staff_accounts(
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[StaffAccountSummary]:
    repository = StaffRepository(session)
    accounts = await repository.list_accounts()
    return [
        StaffAccountSummary(
            id=account.id,
            email=account.email,
            role=account.role.value,
            is_active=account.is_active,
            created_at=account.created_at,
        )
        for account in accounts
    ]


@router.get("/{staff_id}", response_model=StaffAccountDetailResponse)
async def get_staff_account(
    staff_id: str,
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffAccountDetailResponse:
    service = StaffService(session=session)
    try:
        return await service.get_staff_account_detail(staff_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/{staff_id}", response_model=StaffAccountDetailResponse, status_code=status.HTTP_200_OK)
async def update_staff_account(
    staff_id: str,
    payload: StaffAccountUpdateRequest,
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffAccountDetailResponse:
    service = StaffService(session=session)
    try:
        response = await service.update_staff_account(staff_id=staff_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.put("/{staff_id}/access", response_model=StaffAccessConfigResponse, status_code=status.HTTP_200_OK)
async def set_staff_access_mode(
    staff_id: str,
    payload: StaffAccessModeUpdateRequest,
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffAccessConfigResponse:
    service = StaffService(session=session)
    try:
        response = await service.set_staff_access_mode(staff_id=staff_id, mode=payload.mode)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.post("/{staff_id}/access/events", response_model=StaffAccessConfigResponse, status_code=status.HTTP_200_OK)
async def add_staff_access_event(
    staff_id: str,
    payload: StaffEventAccessAddRequest,
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffAccessConfigResponse:
    service = StaffService(session=session)
    try:
        response = await service.add_staff_event_access(staff_id=staff_id, event_id=payload.event_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.delete("/{staff_id}/access/events/{event_id}", response_model=StaffAccessConfigResponse, status_code=status.HTTP_200_OK)
async def remove_staff_access_event(
    staff_id: str,
    event_id: str,
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffAccessConfigResponse:
    service = StaffService(session=session)
    try:
        response = await service.remove_staff_event_access(staff_id=staff_id, event_id=event_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
