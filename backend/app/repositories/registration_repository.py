from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.payment import Payment
from app.models.registration import BatchRegistration, Registration, RegistrationState


CAPACITY_OCCUPYING_STATES = (
    RegistrationState.PENDING_PAYMENT,
    RegistrationState.CONFIRMED,
    RegistrationState.REFUND_REQUESTED,
)


@dataclass
class RegistrationEventContext:
    event: Event


class RegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_event_with_fields(self, event_id: str) -> Event | None:
        result = await self.session.execute(
            select(Event)
            .where(Event.id == event_id)
            .options(selectinload(Event.field_definitions))
        )
        return result.scalar_one_or_none()

    async def email_exists_for_event(self, event_id: str, email: str) -> bool:
        result = await self.session.execute(
            select(Registration.id).where(
                Registration.event_id == event_id,
                func.lower(Registration.email) == email.lower(),
            )
        )
        return result.scalar_one_or_none() is not None

    async def existing_emails_for_event(self, event_id: str, emails: list[str]) -> list[str]:
        if not emails:
            return []
        lowered_emails = [email.lower() for email in emails]
        result = await self.session.execute(
            select(func.lower(Registration.email))
            .where(
                Registration.event_id == event_id,
                func.lower(Registration.email).in_(lowered_emails),
            )
            .distinct()
        )
        return sorted(result.scalars().all())

    async def reg_id_exists(self, reg_id: str) -> bool:
        result = await self.session.execute(select(Registration.id).where(Registration.reg_id == reg_id))
        return result.scalar_one_or_none() is not None

    async def count_capacity_occupying_registrations(self, event_id: str) -> int:
        result = await self.session.execute(
            select(func.count(Registration.id)).where(
                Registration.event_id == event_id,
                Registration.state.in_(CAPACITY_OCCUPYING_STATES),
            )
        )
        return int(result.scalar_one())

    async def count_waitlisted_registrations(self, event_id: str) -> int:
        result = await self.session.execute(
            select(func.count(Registration.id)).where(
                Registration.event_id == event_id,
                Registration.state == RegistrationState.WAITLISTED,
            )
        )
        return int(result.scalar_one())

    async def create_registration(self, registration: Registration) -> Registration:
        self.session.add(registration)
        await self.session.flush()
        return registration

    async def create_batch_registration(self, batch_registration: BatchRegistration) -> BatchRegistration:
        self.session.add(batch_registration)
        await self.session.flush()
        return batch_registration

    async def create_payment(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment
