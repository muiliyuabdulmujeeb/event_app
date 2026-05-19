from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.schemas.refund import (
    RefundRequestCreateRequest,
    RefundRequestCreateResponse,
    RegistrationCancellationRequest,
    RegistrationCancellationResponse,
)
from app.services.email_service import EmailService
from app.services.refund_service import RefundService


router = APIRouter(tags=["public-self-service-registrations"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.patch(
    "/registrations/{reg_id}/cancel",
    response_model=RegistrationCancellationResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_registration(
    reg_id: str,
    payload: RegistrationCancellationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegistrationCancellationResponse:
    service = RefundService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.cancel_registration(reg_id=reg_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.promoted_ticket_email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.post(
    "/registrations/{reg_id}/refund-requests",
    response_model=RefundRequestCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_refund_request(
    reg_id: str,
    payload: RefundRequestCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RefundRequestCreateResponse:
    service = RefundService(session=session, settings=settings)
    try:
        response = await service.create_refund_request(reg_id=reg_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
