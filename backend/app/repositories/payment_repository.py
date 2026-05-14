from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payment(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment
