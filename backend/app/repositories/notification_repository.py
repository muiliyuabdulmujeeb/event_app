from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import StaffNotification, UserNotification
from app.models.staff import StaffAccount


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_unseen_user_notifications(self, reg_id: str) -> Sequence[UserNotification]:
        result = await self.session.execute(
            select(UserNotification)
            .where(
                UserNotification.reg_id == reg_id,
                UserNotification.is_seen.is_(False),
            )
            .order_by(UserNotification.created_at.asc(), UserNotification.id.asc())
        )
        return result.scalars().all()

    async def get_user_notification(self, notification_id: str) -> UserNotification | None:
        result = await self.session.execute(
            select(UserNotification).where(UserNotification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def create_user_notification(self, *, reg_id: str, title: str, body: str) -> UserNotification:
        notification = UserNotification(reg_id=reg_id, title=title, body=body, is_seen=False)
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def create_staff_notification(self, *, staff_id: str, title: str, body: str) -> StaffNotification:
        notification = StaffNotification(staff_id=staff_id, title=title, body=body, is_read=False)
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_active_staff_accounts(self) -> Sequence[StaffAccount]:
        result = await self.session.execute(
            select(StaffAccount)
            .where(StaffAccount.is_active.is_(True))
            .order_by(StaffAccount.created_at.asc(), StaffAccount.email.asc())
            .options(selectinload(StaffAccount.access_mode_record))
        )
        return result.scalars().all()
