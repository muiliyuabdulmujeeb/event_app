from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.notification import StaffNotification
from app.models.registration import Registration, RegistrationFieldValue
from app.models.staff import RefreshToken, StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffEventAccess


class StaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> StaffAccount | None:
        result = await self.session.execute(select(StaffAccount).where(StaffAccount.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, staff_id: str) -> StaffAccount | None:
        result = await self.session.execute(select(StaffAccount).where(StaffAccount.id == staff_id))
        return result.scalar_one_or_none()

    async def get_by_id_with_access(self, staff_id: str) -> StaffAccount | None:
        result = await self.session.execute(
            select(StaffAccount)
            .where(StaffAccount.id == staff_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(StaffAccount.access_mode_record),
                selectinload(StaffAccount.event_access_entries).selectinload(StaffEventAccess.event),
            )
        )
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

    async def get_event(self, event_id: str) -> Event | None:
        result = await self.session.execute(select(Event).where(Event.id == event_id))
        return result.scalar_one_or_none()

    async def get_registration_by_reg_id(self, reg_id: str) -> Registration | None:
        result = await self.session.execute(
            select(Registration)
            .where(Registration.reg_id == reg_id)
            .options(
                selectinload(Registration.event),
                selectinload(Registration.payment),
                selectinload(Registration.payments),
                selectinload(Registration.batch_registration),
                selectinload(Registration.field_values).selectinload(RegistrationFieldValue.field_definition),
            )
        )
        return result.scalar_one_or_none()

    async def list_registrations_by_email(self, email: str) -> Sequence[Registration]:
        result = await self.session.execute(
            select(Registration)
            .where(Registration.email == email)
            .order_by(Registration.registered_at.desc(), Registration.reg_id)
            .options(
                selectinload(Registration.event),
                selectinload(Registration.payment),
                selectinload(Registration.payments),
                selectinload(Registration.batch_registration),
                selectinload(Registration.field_values).selectinload(RegistrationFieldValue.field_definition),
            )
        )
        return result.scalars().all()

    async def list_unread_notifications(self, staff_id: str) -> Sequence[StaffNotification]:
        result = await self.session.execute(
            select(StaffNotification)
            .where(
                StaffNotification.staff_id == staff_id,
                StaffNotification.is_read.is_(False),
            )
            .order_by(StaffNotification.created_at.desc(), StaffNotification.id)
        )
        return result.scalars().all()

    async def get_staff_notification(self, notification_id: str, staff_id: str) -> StaffNotification | None:
        result = await self.session.execute(
            select(StaffNotification).where(
                StaffNotification.id == notification_id,
                StaffNotification.staff_id == staff_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_event_access(self, staff_id: str, event_id: str) -> StaffEventAccess | None:
        result = await self.session.execute(
            select(StaffEventAccess).where(
                StaffEventAccess.staff_id == staff_id,
                StaffEventAccess.event_id == event_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_access_mode(self, staff: StaffAccount, mode: StaffAccessMode) -> StaffAccessModeRecord:
        if staff.access_mode_record is None:
            record = StaffAccessModeRecord(staff_id=staff.id, mode=mode)
            self.session.add(record)
            staff.access_mode_record = record
        else:
            staff.access_mode_record.mode = mode
        await self.session.flush()
        return staff.access_mode_record

    async def add_event_access(self, staff_id: str, event_id: str) -> StaffEventAccess:
        access = StaffEventAccess(staff_id=staff_id, event_id=event_id)
        self.session.add(access)
        await self.session.flush()
        return access

    async def remove_event_access(self, access: StaffEventAccess) -> None:
        await self.session.delete(access)
        await self.session.flush()
