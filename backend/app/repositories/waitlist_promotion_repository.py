from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.registration import Registration
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus


ACTIVE_WAITLIST_PROMOTION_STATUSES = (
    WaitlistPromotionOfferStatus.OFFERED,
    WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED,
)


class WaitlistPromotionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_offer(self, offer: WaitlistPromotionOffer) -> WaitlistPromotionOffer:
        self.session.add(offer)
        await self.session.flush()
        return offer

    async def get_by_public_token(
        self,
        public_token: str,
        *,
        for_update: bool = False,
    ) -> WaitlistPromotionOffer | None:
        query = (
            select(WaitlistPromotionOffer)
            .where(WaitlistPromotionOffer.public_token == public_token)
            .options(
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.event),
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.payment),
                selectinload(WaitlistPromotionOffer.payment),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_registration_id(
        self,
        registration_id: str,
        *,
        for_update: bool = False,
    ) -> WaitlistPromotionOffer | None:
        query = (
            select(WaitlistPromotionOffer)
            .where(WaitlistPromotionOffer.registration_id == registration_id)
            .options(
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.event),
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.payment),
                selectinload(WaitlistPromotionOffer.payment),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_expired_active_offers(self, now: datetime) -> Sequence[WaitlistPromotionOffer]:
        result = await self.session.execute(
            select(WaitlistPromotionOffer)
            .where(
                WaitlistPromotionOffer.status.in_(ACTIVE_WAITLIST_PROMOTION_STATUSES),
                WaitlistPromotionOffer.offer_expires_at < now,
            )
            .options(
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.event),
                selectinload(WaitlistPromotionOffer.registration).selectinload(Registration.payment),
                selectinload(WaitlistPromotionOffer.payment),
            )
            .with_for_update()
        )
        return result.scalars().all()
