from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventState
from app.models.registration import Registration, RegistrationState


@dataclass
class EventSummaryRow:
    event: Event
    registration_count: int
    confirmed_count: int


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: str, *, include_fields: bool = False) -> Event | None:
        query: Select[tuple[Event]] = select(Event).where(Event.id == event_id)
        if include_fields:
            query = query.options(selectinload(Event.field_definitions))
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
            .group_by(Event.id)
            .order_by(Event.created_at.desc())
        )
        result = await self.session.execute(query)
        return [
            EventSummaryRow(
                event=event,
                registration_count=registration_count,
                confirmed_count=confirmed_count_value,
            )
            for event, registration_count, confirmed_count_value in result.all()
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

