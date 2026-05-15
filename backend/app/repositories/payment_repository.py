from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import Payment, PaymentStatus
from app.models.registration import BatchRegistration, Registration, RegistrationState


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payment(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_reference(
        self,
        reference: str,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        query = (
            select(Payment)
            .where(Payment.payment_reference == reference)
            .options(
                selectinload(Payment.registration).selectinload(Registration.event),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.event),
            )
        )
        if for_update:
            query = query.with_for_update()

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_expired_pending_payments(self, cutoff: datetime) -> list[Payment]:
        query = (
            select(Payment)
            .where(
                Payment.status == PaymentStatus.PENDING,
                or_(
                    Payment.registration.has(Registration.registered_at < cutoff),
                    Payment.batch_registration.has(BatchRegistration.created_at < cutoff),
                ),
            )
            .options(
                selectinload(Payment.registration).selectinload(Registration.event),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.event),
            )
            .with_for_update()
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def list_pending_registrations_for_batch(self, batch_id: str) -> list[Registration]:
        result = await self.session.execute(
            select(Registration)
            .where(
                Registration.batch_id == batch_id,
                Registration.state == RegistrationState.PENDING_PAYMENT,
            )
            .order_by(Registration.registered_at)
        )
        return list(result.scalars().all())
