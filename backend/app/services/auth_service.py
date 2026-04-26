from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    access_token_expiry,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    refresh_token_expiry,
    utc_now,
    verify_password,
)
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import LoginResponse, RefreshAccessTokenResponse

INVALID_LOGIN_DETAIL = "Invalid email or password."
DISABLED_ACCOUNT_DETAIL = "This account has been disabled."
INVALID_REFRESH_DETAIL = "Refresh token is invalid or has expired. Please log in again."


@dataclass
class AuthService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = StaffRepository(self.session)

    async def login(self, *, email: str, password: str) -> LoginResponse:
        account = await self.repository.get_by_email(email)
        if account is None or not verify_password(password, account.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_DETAIL)

        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DISABLED_ACCOUNT_DETAIL)

        access_token, _ = create_access_token(account=account, settings=self.settings)
        refresh_token, refresh_expires_at, refresh_token_id = create_refresh_token(
            account=account,
            settings=self.settings,
        )
        await self.repository.create_refresh_token(
            token_id=refresh_token_id,
            staff_id=account.id,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
        )
        await self.session.commit()

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            access_token_expires_in=int(access_token_expiry(self.settings).total_seconds()),
            refresh_token_expires_in=int(refresh_token_expiry(self.settings).total_seconds()),
            role=account.role.value,
        )

    async def refresh_access_token(self, *, refresh_token: str) -> RefreshAccessTokenResponse:
        try:
            payload = decode_token(refresh_token, settings=self.settings)
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_DETAIL) from exc

        if payload.get("token_type") != REFRESH_TOKEN_TYPE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_DETAIL)

        token_id = payload.get("jti")
        staff_id = payload.get("sub")
        if not isinstance(token_id, str) or not isinstance(staff_id, str):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_DETAIL)

        stored_token = await self.repository.get_refresh_token(token_id)
        if (
            stored_token is None
            or stored_token.staff_id != staff_id
            or stored_token.revoked_at is not None
            or stored_token.expires_at <= utc_now()
            or stored_token.token_hash != hash_token(refresh_token)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_DETAIL)

        account = await self.repository.get_by_id(staff_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_DETAIL)

        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DISABLED_ACCOUNT_DETAIL)

        access_token, _ = create_access_token(account=account, settings=self.settings)
        return RefreshAccessTokenResponse(
            access_token=access_token,
            token_type="bearer",
            access_token_expires_in=int(access_token_expiry(self.settings).total_seconds()),
        )
