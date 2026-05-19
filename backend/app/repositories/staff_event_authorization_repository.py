from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.staff import StaffAccount
from app.models.staff_event_authorization import StaffEventAuthorization


class StaffEventAuthorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_event_and_staff(
        self,
        *,
        event_id: str,
        staff_id: str,
        for_update: bool = False,
    ) -> StaffEventAuthorization | None:
        query = (
            select(StaffEventAuthorization)
            .where(
                StaffEventAuthorization.event_id == event_id,
                StaffEventAuthorization.staff_id == staff_id,
            )
            .options(selectinload(StaffEventAuthorization.staff))
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_active_for_event(self, event_id: str) -> Sequence[StaffEventAuthorization]:
        result = await self.session.execute(
            select(StaffEventAuthorization)
            .where(
                StaffEventAuthorization.event_id == event_id,
                StaffEventAuthorization.revoked_at.is_(None),
            )
            .join(StaffAccount, StaffAccount.id == StaffEventAuthorization.staff_id)
            .options(selectinload(StaffEventAuthorization.staff))
            .order_by(StaffAccount.email.asc(), StaffEventAuthorization.staff_id.asc())
        )
        return result.scalars().all()

    async def create(self, authorization: StaffEventAuthorization) -> StaffEventAuthorization:
        self.session.add(authorization)
        await self.session.flush()
        return authorization

