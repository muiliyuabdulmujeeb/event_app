from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception, error_response
from app.schemas.registration import (
    BatchRegistrationCreateRequest,
    BatchRegistrationCreateResponse,
    RegistrationCreateRequest,
    RegistrationCreateResponse,
)
from app.services.email_service import EmailService
from app.services.manual_review_service import ManualReviewService
from app.services.registration_service import RegistrationService
from app.schemas.manual_review import RegistrationPaymentInitializationResponse

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
    email_service = EmailService(settings=settings)
    try:
        result = await service.create_single_registration(event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        if result.ticket_email_message is not None:
            email_service.enqueue_message(result.ticket_email_message)
        return result.response
    except AppError as exc:
        await session.rollback()
        if exc.extra:
            return error_response(exc)
        raise as_http_exception(exc) from exc


@router.post("/register/{event_id}/batch", response_model=BatchRegistrationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_batch_registration(
    event_id: str,
    payload: BatchRegistrationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> BatchRegistrationCreateResponse:
    service = RegistrationService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.create_batch_registration(event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.ticket_email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        if exc.extra:
            return error_response(exc)
        raise as_http_exception(exc) from exc


@router.post(
    "/registrations/{reg_id}/payments/initialize",
    response_model=RegistrationPaymentInitializationResponse,
    status_code=status.HTTP_200_OK,
)
async def initialize_registration_payment(
    reg_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegistrationPaymentInitializationResponse:
    service = ManualReviewService(session=session, settings=settings)
    try:
        response = await service.initialize_registration_payment(reg_id=reg_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
