from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff import RefreshToken, StaffAccount


class StaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> StaffAccount | None:
        result = await self.session.execute(select(StaffAccount).where(StaffAccount.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, staff_id: str) -> StaffAccount | None:
        result = await self.session.execute(select(StaffAccount).where(StaffAccount.id == staff_id))
        return result.scalar_one_or_none()

    async def list_accounts(self) -> Sequence[StaffAccount]:
        result = await self.session.execute(select(StaffAccount).order_by(StaffAccount.created_at, StaffAccount.email))
        return result.scalars().all()

    async def create_refresh_token(
        self,
        *,
        token_id: str,
        staff_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            id=token_id,
            staff_id=staff_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(refresh_token)
        await self.session.flush()
        return refresh_token

    async def get_refresh_token(self, token_id: str) -> RefreshToken | None:
        result = await self.session.execute(select(RefreshToken).where(RefreshToken.id == token_id))
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_id: str, revoked_at: datetime) -> RefreshToken | None:
        refresh_token = await self.get_refresh_token(token_id)
        if refresh_token is None:
            return None
        refresh_token.revoked_at = revoked_at
        await self.session.flush()
        return refresh_token
