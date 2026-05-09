from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception, error_response
from app.schemas.registration import RegistrationCreateRequest, RegistrationCreateResponse
from app.services.registration_service import RegistrationService
from app.workers.email_tasks import send_email_task

router = APIRouter(tags=["public-registrations"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.post("/register/{event_id}", response_model=RegistrationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_single_registration(
    event_id: str,
    payload: RegistrationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegistrationCreateResponse:
    service = RegistrationService(session=session, settings=settings)
    try:
        result = await service.create_single_registration(event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        if result.ticket_email_payload is not None:
            send_email_task.delay(result.ticket_email_payload)
        return result.response
    except AppError as exc:
        await session.rollback()
        if exc.extra:
            return error_response(exc)
        raise as_http_exception(exc) from exc
