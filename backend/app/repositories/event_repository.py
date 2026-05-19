from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventState
from app.models.exception_registration_offer import ExceptionRegistrationOffer
from app.models.refund_request import RefundRequest, RefundRequestStatus
from app.models.registration import Registration, RegistrationState


@dataclass
class EventSummaryRow:
    event: Event
    registration_count: int
    confirmed_count: int
    capacity_override_count: int


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(
        self,
        event_id: str,
        *,
        include_fields: bool = False,
        for_update: bool = False,
    ) -> Event | None:
        query: Select[tuple[Event]] = select(Event).where(Event.id == event_id)
        if include_fields:
            query = query.options(selectinload(Event.field_definitions))
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_published_by_id(self, event_id: str, *, include_fields: bool = False) -> Event | None:
        query: Select[tuple[Event]] = select(Event).where(
            Event.id == event_id,
            Event.state == EventState.PUBLISHED,
        )
        if include_fields:
            query = query.options(selectinload(Event.field_definitions))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_admin_events(self) -> list[EventSummaryRow]:
        registration_counts = (
            select(
                Registration.event_id.label("event_id"),
                func.count(Registration.id).label("registration_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (Registration.state == RegistrationState.CONFIRMED, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("confirmed_count"),
            )
            .group_by(Registration.event_id)
            .subquery()
        )
        capacity_override_counts = (
            select(
                ExceptionRegistrationOffer.event_id.label("event_id"),
                func.count(ExceptionRegistrationOffer.id).label("capacity_override_count"),
            )
            .join(Registration, Registration.id == ExceptionRegistrationOffer.used_registration_id)
            .where(
                ExceptionRegistrationOffer.capacity_override.is_(True),
                Registration.state.in_(
                    [
                        RegistrationState.PENDING_PAYMENT,
                        RegistrationState.CONFIRMED,
                    ]
                ),
            )
            .group_by(ExceptionRegistrationOffer.event_id)
            .subquery()
        )
        query = (
            select(
                Event,
                func.coalesce(registration_counts.c.registration_count, 0),
                func.coalesce(registration_counts.c.confirmed_count, 0),
                func.coalesce(capacity_override_counts.c.capacity_override_count, 0),
            )
            .outerjoin(registration_counts, registration_counts.c.event_id == Event.id)
            .outerjoin(capacity_override_counts, capacity_override_counts.c.event_id == Event.id)
            .order_by(Event.created_at.desc())
        )
        result = await self.session.execute(query)
        return [
            EventSummaryRow(
                event=event,
                registration_count=registration_count,
                confirmed_count=confirmed_count_value,
                capacity_override_count=capacity_override_count,
            )
            for event, registration_count, confirmed_count_value, capacity_override_count in result.all()
        ]

    async def list_published_events(
        self,
        *,
        search: str | None = None,
        is_free: bool | None = None,
    ) -> list[EventSummaryRow]:
        confirmed_count = func.coalesce(
            func.sum(
                case(
                    (Registration.state == RegistrationState.CONFIRMED, 1),
                    else_=0,
                )
            ),
            0,
        )
        query = (
            select(
                Event,
                func.count(Registration.id),
                confirmed_count,
            )
            .outerjoin(Registration, Registration.event_id == Event.id)
            .where(Event.state == EventState.PUBLISHED)
            .group_by(Event.id)
            .order_by(Event.event_date.asc())
        )
        if search:
            query = query.where(Event.title.ilike(f"%{search.strip()}%"))
        if is_free is not None:
            query = query.where(Event.is_free.is_(is_free))

        result = await self.session.execute(query)
        return [
            EventSummaryRow(
                event=event,
                registration_count=registration_count,
                confirmed_count=confirmed_count_value,
                capacity_override_count=0,
            )
            for event, registration_count, confirmed_count_value in result.all()
        ]

    async def get_registration_counts(self, event_id: str) -> dict[str, int]:
        query = (
            select(Registration.state, func.count(Registration.id))
            .where(Registration.event_id == event_id)
            .group_by(Registration.state)
        )
        result = await self.session.execute(query)
        counts = {state.value: count for state, count in result.all()}
        return counts

    async def get_refund_request_counts(self, event_id: str) -> dict[str, int]:
        query = (
            select(RefundRequest.status, func.count(RefundRequest.id))
            .join(Registration, Registration.id == RefundRequest.registration_id)
            .where(Registration.event_id == event_id)
            .group_by(RefundRequest.status)
        )
        result = await self.session.execute(query)
        counts = {status.value: count for status, count in result.all()}
        return {
            RefundRequestStatus.REQUESTED.value: counts.get(RefundRequestStatus.REQUESTED.value, 0),
            RefundRequestStatus.COMPLETED.value: counts.get(RefundRequestStatus.COMPLETED.value, 0),
        }

    async def list_capacity_override_counts(self, event_ids: list[str]) -> dict[str, int]:
        if not event_ids:
            return {}
        query = (
            select(
                ExceptionRegistrationOffer.event_id,
                func.count(ExceptionRegistrationOffer.id),
            )
            .join(Registration, Registration.id == ExceptionRegistrationOffer.used_registration_id)
            .where(
                ExceptionRegistrationOffer.event_id.in_(event_ids),
                ExceptionRegistrationOffer.capacity_override.is_(True),
                Registration.state.in_(
                    [
                        RegistrationState.PENDING_PAYMENT,
                        RegistrationState.CONFIRMED,
                    ]
                ),
            )
            .group_by(ExceptionRegistrationOffer.event_id)
        )
        result = await self.session.execute(query)
        return {event_id: count for event_id, count in result.all()}
