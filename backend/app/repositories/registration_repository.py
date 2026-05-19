from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.payment import Payment
from app.models.refund_request import RefundRequest, RefundRequestStatus
from app.models.registration import BatchRegistration, Registration, RegistrationFieldValue, RegistrationState


CAPACITY_OCCUPYING_STATES = (
    RegistrationState.PENDING_PAYMENT,
    RegistrationState.CONFIRMED,
)

DUPLICATE_BLOCKING_STATES = (
    RegistrationState.PENDING_PAYMENT,
    RegistrationState.CONFIRMED,
    RegistrationState.WAITLISTED,
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

    async def lock_event(self, event_id: str) -> Event | None:
        result = await self.session.execute(
            select(Event)
            .where(Event.id == event_id)
            .with_for_update()
            .options(selectinload(Event.field_definitions))
        )
        return result.scalar_one_or_none()

    async def email_exists_for_event(self, event_id: str, email: str) -> bool:
        requested_refund_exists = exists(
            select(RefundRequest.id).where(
                RefundRequest.registration_id == Registration.id,
                RefundRequest.status == RefundRequestStatus.REQUESTED,
            )
        )
        result = await self.session.execute(
            select(Registration.id).where(
                Registration.event_id == event_id,
                func.lower(Registration.email) == email.lower(),
                or_(
                    Registration.state.in_(DUPLICATE_BLOCKING_STATES),
                    requested_refund_exists,
                ),
            )
        )
        return result.scalar_one_or_none() is not None

    async def existing_emails_for_event(self, event_id: str, emails: list[str]) -> list[str]:
        if not emails:
            return []
        lowered_emails = [email.lower() for email in emails]
        requested_refund_exists = exists(
            select(RefundRequest.id).where(
                RefundRequest.registration_id == Registration.id,
                RefundRequest.status == RefundRequestStatus.REQUESTED,
            )
        )
        result = await self.session.execute(
            select(func.lower(Registration.email))
            .where(
                Registration.event_id == event_id,
                func.lower(Registration.email).in_(lowered_emails),
                or_(
                    Registration.state.in_(DUPLICATE_BLOCKING_STATES),
                    requested_refund_exists,
                ),
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

    async def get_registration_by_reg_id(
        self,
        reg_id: str,
        *,
        for_update: bool = False,
    ) -> Registration | None:
        query = (
            select(Registration)
            .where(Registration.reg_id == reg_id)
            .options(
                selectinload(Registration.event).selectinload(Event.field_definitions),
                selectinload(Registration.payment),
                selectinload(Registration.payments),
                selectinload(Registration.field_values).selectinload(RegistrationFieldValue.field_definition),
                selectinload(Registration.refund_requests),
                selectinload(Registration.user_notifications),
                selectinload(Registration.waitlist_promotion_offer),
                selectinload(Registration.exception_offer),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_registrations_for_event(
        self,
        event_id: str,
        *,
        states: Sequence[RegistrationState] | None = None,
        for_update: bool = False,
    ) -> list[Registration]:
        query = (
            select(Registration)
            .where(Registration.event_id == event_id)
            .order_by(Registration.registered_at.asc(), Registration.reg_id.asc())
            .options(
                selectinload(Registration.event).selectinload(Event.field_definitions),
                selectinload(Registration.payment),
                selectinload(Registration.payments),
                selectinload(Registration.field_values).selectinload(RegistrationFieldValue.field_definition),
                selectinload(Registration.refund_requests),
                selectinload(Registration.waitlist_promotion_offer),
                selectinload(Registration.exception_offer),
            )
        )
        if states is not None:
            query = query.where(Registration.state.in_(list(states)))
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_next_waitlisted_registration(
        self,
        event_id: str,
        *,
        for_update: bool = False,
    ) -> Registration | None:
        query = (
            select(Registration)
            .where(
                Registration.event_id == event_id,
                Registration.state == RegistrationState.WAITLISTED,
            )
            .order_by(Registration.waitlist_position.asc(), Registration.registered_at.asc(), Registration.reg_id.asc())
            .options(
                selectinload(Registration.event).selectinload(Event.field_definitions),
                selectinload(Registration.payment),
                selectinload(Registration.payments),
                selectinload(Registration.field_values).selectinload(RegistrationFieldValue.field_definition),
                selectinload(Registration.exception_offer),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none()
