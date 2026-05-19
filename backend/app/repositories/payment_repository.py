from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import Payment, PaymentStatus
from app.models.registration import BatchRegistration, Registration, RegistrationState
from app.models.waitlist_promotion_offer import WaitlistPromotionOfferStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payment(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_next_registration_attempt_number(self, registration_id: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(Payment.attempt_number), 0) + 1).where(
                Payment.registration_id == registration_id
            )
        )
        return int(result.scalar_one())

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
                selectinload(Payment.registration).selectinload(Registration.payment),
                selectinload(Payment.registration).selectinload(Registration.payments),
                selectinload(Payment.registration).selectinload(Registration.waitlist_promotion_offer),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.event),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.payment),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.payments),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.waitlist_promotion_offer),
            )
        )
        if for_update:
            query = query.with_for_update()

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_expired_pending_payments(self, cutoff: datetime) -> list[Payment]:
        query = (
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.created_at.asc(), Payment.id.asc())
            .options(
                selectinload(Payment.registration).selectinload(Registration.event),
                selectinload(Payment.registration).selectinload(Registration.payment),
                selectinload(Payment.registration).selectinload(Registration.payments),
                selectinload(Payment.registration).selectinload(Registration.waitlist_promotion_offer),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.event),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.payment),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.payments),
                selectinload(Payment.batch_registration)
                .selectinload(BatchRegistration.registrations)
                .selectinload(Registration.waitlist_promotion_offer),
            )
            .with_for_update()
        )
        result = await self.session.execute(query)
        candidates = list(result.scalars().unique().all())
        expired: list[Payment] = []
        for payment in candidates:
            if payment.registration is not None:
                offer = payment.registration.waitlist_promotion_offer
                if (
                    offer is not None
                    and offer.status
                    in {
                        WaitlistPromotionOfferStatus.OFFERED,
                        WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED,
                    }
                ):
                    continue
                if payment.registration.registered_at < cutoff:
                    expired.append(payment)
                continue

            if payment.batch_registration is not None and payment.batch_registration.created_at < cutoff:
                expired.append(payment)

        return expired

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

    async def list_registration_payments(self, registration_id: str) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.registration_id == registration_id)
            .order_by(Payment.attempt_number.asc(), Payment.created_at.asc(), Payment.id.asc())
        )
        return list(result.scalars().all())
