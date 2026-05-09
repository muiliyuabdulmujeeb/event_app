from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, as_http_exception
from app.core.dependencies import get_db_session, require_admin
from app.models.staff import StaffAccount
from app.schemas.event import (
    AdminEventDetailResponse,
    AdminEventListResponse,
    EventCreateRequest,
    EventStateUpdateRequest,
    EventUpdateRequest,
)
from app.services.event_service import (
    EventService,
)

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


@router.get("", response_model=AdminEventListResponse)
async def list_admin_events(
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventListResponse:
    service = EventService(session=session)
    return await service.list_admin_events()


@router.get("/{event_id}", response_model=AdminEventDetailResponse)
async def get_admin_event_detail(
    event_id: str,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.get_admin_event_detail(event_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.post("", response_model=AdminEventDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreateRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.create_event(payload=payload, created_by=account)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/{event_id}", response_model=AdminEventDetailResponse)
async def update_event(
    event_id: str,
    payload: EventUpdateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.update_event(event_id=event_id, payload=payload)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/{event_id}/state", response_model=AdminEventDetailResponse)
async def update_event_state(
    event_id: str,
    payload: EventStateUpdateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.update_event_state(event_id=event_id, payload=payload)
    except AppError as exc:
        raise as_http_exception(exc) from exc
