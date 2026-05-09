from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EventConflictError, EventNotFoundError, EventValidationError
from app.models.event import Event, EventFieldDefinition, EventState, OverflowRule
from app.models.registration import RegistrationState
from app.models.staff import StaffAccount
from app.repositories.event_repository import EventRepository, EventSummaryRow
from app.schemas.event import (
    AdminEventDetailResponse,
    AdminEventListResponse,
    AdminEventSummaryResponse,
    EventCreateRequest,
    EventCustomFieldInput,
    EventCustomFieldResponse,
    EventRegistrationCountsResponse,
    EventStateUpdateRequest,
    EventUpdateRequest,
    PublicEventDetailResponse,
    PublicEventListResponse,
    PublicEventSummaryResponse,
)


ALLOWED_EVENT_STATE_TRANSITIONS: dict[EventState, set[EventState]] = {
    EventState.DRAFT: {EventState.PUBLISHED},
    EventState.PUBLISHED: {EventState.COMPLETED, EventState.CANCELLED},
    EventState.COMPLETED: set(),
    EventState.CANCELLED: set(),
}


@dataclass
class EventService:
    session: AsyncSession

    def __post_init__(self) -> None:
        self.repository = EventRepository(self.session)

    async def create_event(self, payload: EventCreateRequest, created_by: StaffAccount) -> AdminEventDetailResponse:
        event = Event(
            title=payload.title,
            description=payload.description,
            event_date=payload.event_date,
            location=payload.location,
            prefix=payload.prefix,
            price=payload.price,
            capacity=payload.capacity,
            overflow_rule=self._normalize_overflow_rule(payload.capacity, payload.overflow_rule),
            state=EventState.DRAFT,
            created_by=created_by.id,
        )
        event.field_definitions = self._build_field_definitions(payload.custom_fields)

        try:
            await self.repository.create(event)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise self._map_integrity_error(exc) from exc

        await self.session.refresh(event)
        event = await self._get_event_or_raise(event.id)
        return await self._build_admin_detail_response(event)

    async def list_admin_events(self) -> AdminEventListResponse:
        rows = await self.repository.list_admin_events()
        return AdminEventListResponse(
            events=[self._build_admin_summary_response(row) for row in rows],
            total=len(rows),
        )

    async def get_admin_event_detail(self, event_id: str) -> AdminEventDetailResponse:
        event = await self._get_event_or_raise(event_id)
        return await self._build_admin_detail_response(event)

    async def update_event(self, event_id: str, payload: EventUpdateRequest) -> AdminEventDetailResponse:
        event = await self._get_event_or_raise(event_id)

        if payload.prefix is not None and payload.prefix != event.prefix:
            raise EventValidationError("Event prefix cannot be changed after creation.")

        if payload.title is not None:
            event.title = payload.title
        if payload.description is not None:
            event.description = payload.description
        if payload.event_date is not None:
            event.event_date = payload.event_date
        if payload.location is not None:
            event.location = payload.location
        if payload.price is not None:
            event.price = payload.price
        if "capacity" in payload.model_fields_set:
            event.capacity = payload.capacity

        selected_overflow_rule = payload.overflow_rule if payload.overflow_rule is not None else event.overflow_rule
        event.overflow_rule = self._normalize_overflow_rule(event.capacity, selected_overflow_rule)

        if payload.custom_fields is not None:
            event.field_definitions = self._build_field_definitions(payload.custom_fields)

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise self._map_integrity_error(exc) from exc

        event = await self._get_event_or_raise(event_id)
        return await self._build_admin_detail_response(event)

    async def update_event_state(
        self,
        event_id: str,
        payload: EventStateUpdateRequest,
    ) -> AdminEventDetailResponse:
        event = await self._get_event_or_raise(event_id)

        if payload.state not in ALLOWED_EVENT_STATE_TRANSITIONS[event.state]:
            raise EventValidationError(
                f"Invalid event state transition from '{event.state.value}' to '{payload.state.value}'."
            )

        event.state = payload.state
        await self.session.commit()
        event = await self._get_event_or_raise(event_id)
        return await self._build_admin_detail_response(event)

    async def list_public_events(
        self,
        *,
        search: str | None = None,
        is_free: bool | None = None,
    ) -> PublicEventListResponse:
        rows = await self.repository.list_published_events(search=search, is_free=is_free)
        return PublicEventListResponse(
            events=[self._build_public_summary_response(row) for row in rows],
            total=len(rows),
        )

    async def get_public_event_detail(self, event_id: str) -> PublicEventDetailResponse:
        event = await self.repository.get_published_by_id(event_id, include_fields=True)
        if event is None:
            raise EventNotFoundError("Event not found.")

        counts = await self.repository.get_registration_counts(event.id)
        confirmed_count = counts.get(RegistrationState.CONFIRMED.value, 0)
        return PublicEventDetailResponse(
            id=event.id,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            location=event.location,
            price=event.price,
            is_free=event.is_free,
            state=event.state,
            capacity=event.capacity,
            slots_remaining=self._compute_slots_remaining(event.capacity, confirmed_count),
            custom_fields=[EventCustomFieldResponse.model_validate(field) for field in event.field_definitions],
        )

    async def _get_event_or_raise(self, event_id: str) -> Event:
        event = await self.repository.get_by_id(event_id, include_fields=True)
        if event is None:
            raise EventNotFoundError("Event not found.")
        return event

    async def _build_admin_detail_response(self, event: Event) -> AdminEventDetailResponse:
        counts = await self.repository.get_registration_counts(event.id)
        registration_counts = EventRegistrationCountsResponse(
            total_registrations=sum(counts.values()),
            pending_payment=counts.get(RegistrationState.PENDING_PAYMENT.value, 0),
            confirmed=counts.get(RegistrationState.CONFIRMED.value, 0),
            failed=counts.get(RegistrationState.FAILED.value, 0),
            cancelled=counts.get(RegistrationState.CANCELLED.value, 0),
            refund_requested=counts.get(RegistrationState.REFUND_REQUESTED.value, 0),
            refunded=counts.get(RegistrationState.REFUNDED.value, 0),
            waitlisted=counts.get(RegistrationState.WAITLISTED.value, 0),
        )
        return AdminEventDetailResponse(
            id=event.id,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            location=event.location,
            prefix=event.prefix,
            price=event.price,
            is_free=event.is_free,
            capacity=event.capacity,
            overflow_rule=event.overflow_rule,
            state=event.state,
            slots_remaining=self._compute_slots_remaining(event.capacity, registration_counts.confirmed),
            custom_fields=[EventCustomFieldResponse.model_validate(field) for field in event.field_definitions],
            registration_counts=registration_counts,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def _build_admin_summary_response(self, row: EventSummaryRow) -> AdminEventSummaryResponse:
        event = row.event
        return AdminEventSummaryResponse(
            id=event.id,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            location=event.location,
            prefix=event.prefix,
            price=event.price,
            is_free=event.is_free,
            capacity=event.capacity,
            overflow_rule=event.overflow_rule,
            state=event.state,
            registration_count=row.registration_count,
            confirmed_count=row.confirmed_count,
            slots_remaining=self._compute_slots_remaining(event.capacity, row.confirmed_count),
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def _build_public_summary_response(self, row: EventSummaryRow) -> PublicEventSummaryResponse:
        event = row.event
        return PublicEventSummaryResponse(
            id=event.id,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            location=event.location,
            price=event.price,
            is_free=event.is_free,
            state=event.state,
            capacity=event.capacity,
            slots_remaining=self._compute_slots_remaining(event.capacity, row.confirmed_count),
        )

    def _build_field_definitions(self, custom_fields: list[EventCustomFieldInput]) -> list[EventFieldDefinition]:
        return [
            EventFieldDefinition(
                label=field.label,
                field_type=field.field_type,
                is_required=field.is_required,
                display_order=field.display_order,
            )
            for field in custom_fields
        ]

    def _normalize_overflow_rule(self, capacity: int | None, overflow_rule: OverflowRule) -> OverflowRule:
        if capacity is None:
            return OverflowRule.HARD_REJECTION
        return overflow_rule

    def _compute_slots_remaining(self, capacity: int | None, confirmed_count: int) -> int | None:
        if capacity is None:
            return None
        return max(capacity - confirmed_count, 0)

    def _map_integrity_error(self, exc: IntegrityError) -> Exception:
        error_text = str(exc.orig).lower()
        if "uq_events_prefix" in error_text or "duplicate key value" in error_text and "prefix" in error_text:
            return EventConflictError("An event with this prefix already exists.")
        if "uq_event_field_definitions_order" in error_text:
            return EventValidationError("custom_fields display_order values must be unique")
        return EventConflictError("The event could not be saved because it conflicts with existing data.")
