from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.exception_registration_offer_audit import ExceptionRegistrationOfferAudit
from app.models.payment import Payment
from app.models.registration import Registration


@dataclass(frozen=True)
class ExceptionOfferListFilters:
    status: ExceptionRegistrationOfferStatus | None = None
    target_email: str | None = None


class ExceptionRegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_offer(self, offer: ExceptionRegistrationOffer) -> ExceptionRegistrationOffer:
        self.session.add(offer)
        await self.session.flush()
        return offer

    async def create_audit_entry(
        self,
        audit_entry: ExceptionRegistrationOfferAudit,
    ) -> ExceptionRegistrationOfferAudit:
        self.session.add(audit_entry)
        await self.session.flush()
        return audit_entry

    async def list_offers_for_event(
        self,
        event_id: str,
        *,
        filters: ExceptionOfferListFilters,
    ) -> list[ExceptionRegistrationOffer]:
        query: Select[tuple[ExceptionRegistrationOffer]] = (
            select(ExceptionRegistrationOffer)
            .where(ExceptionRegistrationOffer.event_id == event_id)
            .order_by(ExceptionRegistrationOffer.created_at.desc())
        )
        if filters.status is not None:
            query = query.where(ExceptionRegistrationOffer.status == filters.status)
        if filters.target_email is not None:
            query = query.where(ExceptionRegistrationOffer.target_email == filters.target_email.lower())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_offer_by_id(
        self,
        *,
        event_id: str,
        offer_id: str,
        for_update: bool = False,
    ) -> ExceptionRegistrationOffer | None:
        query: Select[tuple[ExceptionRegistrationOffer]] = (
            select(ExceptionRegistrationOffer)
            .where(
                ExceptionRegistrationOffer.id == offer_id,
                ExceptionRegistrationOffer.event_id == event_id,
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_offer_by_public_token(
        self,
        public_token: str,
        *,
        for_update: bool = False,
    ) -> ExceptionRegistrationOffer | None:
        query: Select[tuple[ExceptionRegistrationOffer]] = (
            select(ExceptionRegistrationOffer)
            .where(ExceptionRegistrationOffer.public_token == public_token)
            .options(
                selectinload(ExceptionRegistrationOffer.event).selectinload(Event.field_definitions),
                selectinload(ExceptionRegistrationOffer.used_registration)
                .selectinload(Registration.event)
                .selectinload(Event.field_definitions),
                selectinload(ExceptionRegistrationOffer.used_registration).selectinload(Registration.payment),
                selectinload(ExceptionRegistrationOffer.used_registration).selectinload(Registration.payments),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_audit_entries(self, offer_id: str) -> list[ExceptionRegistrationOfferAudit]:
        result = await self.session.execute(
            select(ExceptionRegistrationOfferAudit)
            .where(ExceptionRegistrationOfferAudit.offer_id == offer_id)
            .order_by(ExceptionRegistrationOfferAudit.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_registration_payment(
        self,
        registration_id: str,
    ) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.registration_id == registration_id)
            .order_by(Payment.attempt_number.desc(), Payment.created_at.desc(), Payment.id.desc())
        )
        return result.scalars().first()
