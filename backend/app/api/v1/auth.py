from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.schemas.staff import (
    LoginRequest,
    LoginResponse,
    RefreshAccessTokenRequest,
    RefreshAccessTokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> LoginResponse:
    service = AuthService(session=session, settings=settings)
    try:
        return await service.login(email=payload.email, password=payload.password)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.post("/refresh", response_model=RefreshAccessTokenResponse)
async def refresh_access_token(
    payload: RefreshAccessTokenRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RefreshAccessTokenResponse:
    service = AuthService(session=session, settings=settings)
    try:
        return await service.refresh_access_token(refresh_token=payload.refresh_token)
    except AppError as exc:
        raise as_http_exception(exc) from exc
