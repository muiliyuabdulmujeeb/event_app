from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.schemas.exception_registration import (
    ExceptionOfferRegistrationRequest,
    ExceptionOfferRegistrationResponse,
)
from app.services.email_service import EmailService
from app.services.exception_registration_service import ExceptionRegistrationService


router = APIRouter(tags=["public-exception-registrations"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.post(
    "/registrations/exception-offers/{public_token}/register",
    response_model=ExceptionOfferRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_with_exception_offer(
    public_token: str,
    payload: ExceptionOfferRegistrationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ExceptionOfferRegistrationResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.consume_offer(public_token=public_token, payload=payload)
        await _commit_or_rollback(session)
        if result.ticket_email_message is not None:
            email_service.enqueue_message(result.ticket_email_message)
        return result.response
    except AppError as exc:
        if exc.commit_changes:
            await _commit_or_rollback(session)
        else:
            await session.rollback()
        raise as_http_exception(exc) from exc


@router.get(
    "/registrations/exception-offers/{public_token}/payments/initialize",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def initialize_exception_offer_payment(
    public_token: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RedirectResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    try:
        result = await service.initialize_offer_payment(public_token)
        await _commit_or_rollback(session)
        return RedirectResponse(url=result.checkout_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
