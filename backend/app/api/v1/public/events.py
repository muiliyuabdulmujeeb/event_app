from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, as_http_exception
from app.core.dependencies import get_db_session
from app.schemas.event import PublicEventDetailResponse, PublicEventListResponse
from app.services.event_service import EventService

router = APIRouter(tags=["public-events"])


@router.get("/events", response_model=PublicEventListResponse)
async def list_public_events(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    search: Annotated[str | None, Query()] = None,
    is_free: Annotated[bool | None, Query()] = None,
) -> PublicEventListResponse:
    service = EventService(session=session)
    return await service.list_public_events(search=search, is_free=is_free)


@router.get("/events/{event_id}", response_model=PublicEventDetailResponse)
async def get_public_event_detail(
    event_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PublicEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.get_public_event_detail(event_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc
