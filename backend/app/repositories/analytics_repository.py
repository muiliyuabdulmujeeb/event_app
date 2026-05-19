from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, exists, func, literal, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import EventNotFoundError, ValidationError
from app.models.event import Event, EventFieldDefinition
from app.models.exception_registration_offer import ExceptionRegistrationOffer
from app.models.payment import Payment, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestStatus
from app.models.registration import BatchRegistration, Registration, RegistrationFieldValue, RegistrationState
from app.schemas.analytics import AnalyticsCustomFieldFilter, AnalyticsRegistrationQuery


SORTABLE_COLUMNS = {
    "reg_id",
    "first_name",
    "last_name",
    "email",
    "registration_state",
    "is_checked_in",
    "checked_in_at",
    "registered_at",
    "is_batch",
    "event_title",
    "event_date",
    "amount_paid",
    "payment_status",
    "paid_at",
}
CUSTOM_FIELD_SORT_PREFIX = "custom_field:"


@dataclass(frozen=True)
class AnalyticsRevenueBreakdownRow:
    event_id: str
    title: str
    gross_revenue: int


@dataclass(frozen=True)
class AnalyticsTrendCountRow:
    point_date: date
    count: int


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_events_in_scope(self, event_ids: Sequence[str]) -> list[Event]:
        query = select(Event).order_by(Event.event_date.asc(), Event.id.asc())
        if event_ids:
            query = query.where(Event.id.in_(list(event_ids)))
        result = await self.session.execute(query)
        events = list(result.scalars().all())
        if event_ids and len(events) != len(set(event_ids)):
            raise EventNotFoundError("One or more event_ids do not match existing events.")
        return events

    async def count_filtered_registrations(self, filters: AnalyticsRegistrationQuery) -> int:
        rows_query = self._build_filtered_rows_query(filters)
        result = await self.session.execute(select(func.count()).select_from(rows_query.subquery()))
        return int(result.scalar_one())

    async def list_filtered_registration_rows(
        self,
        filters: AnalyticsRegistrationQuery,
    ) -> list[RowMapping]:
        rows_query = self._build_filtered_rows_query(filters)
        ordered_query = self._apply_sorting(rows_query, filters.sort_by, filters.sort_order)
        paginated_query = ordered_query.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
        result = await self.session.execute(paginated_query)
        return list(result.mappings().all())

    async def stream_filtered_registration_rows(
        self,
        filters: AnalyticsRegistrationQuery,
    ) -> AsyncIterator[RowMapping]:
        rows_query = self._build_filtered_rows_query(filters)
        ordered_query = self._apply_sorting(rows_query, filters.sort_by, filters.sort_order)
        stream = await self.session.stream(ordered_query)
        async for row in stream.mappings():
            yield row

    async def list_custom_field_values(
        self,
        registration_ids: Sequence[str],
    ) -> dict[str, list[dict[str, str]]]:
        if not registration_ids:
            return {}
        result = await self.session.execute(
            select(
                RegistrationFieldValue.registration_id,
                EventFieldDefinition.label,
                RegistrationFieldValue.value,
                EventFieldDefinition.display_order,
            )
            .join(
                EventFieldDefinition,
                EventFieldDefinition.id == RegistrationFieldValue.field_definition_id,
            )
            .where(RegistrationFieldValue.registration_id.in_(list(registration_ids)))
            .order_by(
                RegistrationFieldValue.registration_id.asc(),
                EventFieldDefinition.display_order.asc(),
                EventFieldDefinition.label.asc(),
            )
        )
        values_by_registration: dict[str, list[dict[str, str]]] = defaultdict(list)
        for registration_id, label, value, _ in result.all():
            values_by_registration[registration_id].append({"label": label, "value": value})
        return dict(values_by_registration)

    async def list_custom_field_labels(self, filters: AnalyticsRegistrationQuery) -> list[str]:
        rows_query = self._build_filtered_rows_query(filters).subquery()
        result = await self.session.execute(
            select(EventFieldDefinition.label)
            .join(RegistrationFieldValue, RegistrationFieldValue.field_definition_id == EventFieldDefinition.id)
            .join(rows_query, rows_query.c.registration_id == RegistrationFieldValue.registration_id)
            .group_by(EventFieldDefinition.label)
            .order_by(func.lower(EventFieldDefinition.label).asc())
        )
        return list(result.scalars().all())

    async def get_registration_summary_metrics(self, filters: AnalyticsRegistrationQuery) -> dict[str, int]:
        rows_query = self._build_filtered_rows_query(filters).subquery()
        result = await self.session.execute(
            select(
                func.count().label("total_registrations"),
                func.coalesce(
                    func.sum(case((rows_query.c.registration_state == RegistrationState.CONFIRMED, 1), else_=0)),
                    0,
                ).label("confirmed"),
                func.coalesce(
                    func.sum(case((rows_query.c.registration_state == RegistrationState.CANCELLED, 1), else_=0)),
                    0,
                ).label("cancelled"),
                func.coalesce(
                    func.sum(case((rows_query.c.registration_state == RegistrationState.WAITLISTED, 1), else_=0)),
                    0,
                ).label("waitlisted"),
                func.coalesce(
                    func.sum(case((rows_query.c.refund_status == RefundRequestStatus.COMPLETED, 1), else_=0)),
                    0,
                ).label("refunded"),
                func.coalesce(
                    func.sum(case((rows_query.c.registration_state == RegistrationState.FAILED, 1), else_=0)),
                    0,
                ).label("failed"),
                func.coalesce(func.sum(case((rows_query.c.is_checked_in.is_(True), 1), else_=0)), 0).label(
                    "checked_in_count"
                ),
            )
        )
        row = result.mappings().one()
        return {
            "total_registrations": int(row["total_registrations"]),
            "confirmed": int(row["confirmed"]),
            "cancelled": int(row["cancelled"]),
            "waitlisted": int(row["waitlisted"]),
            "refunded": int(row["refunded"]),
            "failed": int(row["failed"]),
            "checked_in_count": int(row["checked_in_count"]),
        }

    async def get_revenue_metrics(self, filters: AnalyticsRegistrationQuery) -> dict[str, Any]:
        rows_query = self._build_filtered_rows_query(filters).subquery()
        aggregate_result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(case((rows_query.c.payment_status == PaymentStatus.SUCCESSFUL, rows_query.c.amount_paid), else_=0)),
                    0,
                ).label("gross_revenue"),
                func.coalesce(
                    func.sum(case((rows_query.c.refund_status == RefundRequestStatus.COMPLETED, rows_query.c.amount_paid), else_=0)),
                    0,
                ).label("total_refunded"),
            )
        )
        aggregate_row = aggregate_result.mappings().one()
        breakdown_result = await self.session.execute(
            select(
                rows_query.c.event_id,
                rows_query.c.event_title,
                func.coalesce(
                    func.sum(case((rows_query.c.payment_status == PaymentStatus.SUCCESSFUL, rows_query.c.amount_paid), else_=0)),
                    0,
                ).label("gross_revenue"),
            )
            .group_by(rows_query.c.event_id, rows_query.c.event_title)
            .order_by(rows_query.c.event_title.asc(), rows_query.c.event_id.asc())
        )
        revenue_by_event = [
            AnalyticsRevenueBreakdownRow(
                event_id=event_id,
                title=title,
                gross_revenue=int(gross_revenue),
            )
            for event_id, title, gross_revenue in breakdown_result.all()
        ]
        gross_revenue = int(aggregate_row["gross_revenue"])
        total_refunded = int(aggregate_row["total_refunded"])
        return {
            "gross_revenue": gross_revenue,
            "total_refunded": total_refunded,
            "net_revenue": gross_revenue - total_refunded,
            "revenue_by_event": revenue_by_event,
        }

    async def get_registration_trend_counts(
        self,
        filters: AnalyticsRegistrationQuery,
    ) -> list[AnalyticsTrendCountRow]:
        rows_query = self._build_filtered_rows_query(filters).subquery()
        result = await self.session.execute(
            select(
                func.date(rows_query.c.registered_at).label("point_date"),
                func.count().label("count"),
            )
            .group_by(func.date(rows_query.c.registered_at))
            .order_by(func.date(rows_query.c.registered_at).asc())
        )
        return [
            AnalyticsTrendCountRow(point_date=point_date, count=int(count))
            for point_date, count in result.all()
        ]

    async def get_batch_metrics(self, filters: AnalyticsRegistrationQuery) -> dict[str, Decimal | int]:
        rows_query = self._build_filtered_rows_query(filters).subquery()
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(case((rows_query.c.is_batch.is_(False), 1), else_=0)), 0).label(
                    "single_registration_count"
                ),
                func.coalesce(func.sum(case((rows_query.c.is_batch.is_(True), 1), else_=0)), 0).label(
                    "batch_registration_count"
                ),
                func.count(func.distinct(case((rows_query.c.batch_id.is_not(None), rows_query.c.batch_id), else_=None))).label(
                    "batch_submission_count"
                ),
            )
        )
        row = result.mappings().one()
        batch_registration_count = int(row["batch_registration_count"])
        batch_submission_count = int(row["batch_submission_count"])
        average_batch_size = (
            Decimal(batch_registration_count) / Decimal(batch_submission_count)
            if batch_submission_count
            else Decimal("0.0")
        )
        return {
            "single_registration_count": int(row["single_registration_count"]),
            "batch_registration_count": batch_registration_count,
            "batch_submission_count": batch_submission_count,
            "average_batch_size": average_batch_size.quantize(Decimal("0.1")),
        }

    async def get_capacity_metrics(
        self,
        filters: AnalyticsRegistrationQuery,
        events: Sequence[Event],
    ) -> dict[str, int] | None:
        if not events or any(event.capacity is None for event in events):
            return None

        rows_query = self._build_filtered_rows_query(filters).subquery()
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                rows_query.c.registration_state.in_(
                                    [
                                        RegistrationState.CONFIRMED,
                                        RegistrationState.PENDING_PAYMENT,
                                    ]
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("slots_filled"),
                func.coalesce(
                    func.sum(case((rows_query.c.registration_state == RegistrationState.WAITLISTED, 1), else_=0)),
                    0,
                ).label("waitlist_length"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    rows_query.c.capacity_override_applied.is_(True),
                                    rows_query.c.registration_state.in_(
                                        [
                                            RegistrationState.CONFIRMED,
                                            RegistrationState.PENDING_PAYMENT,
                                        ]
                                    ),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("capacity_override_count"),
            )
        )
        row = result.mappings().one()
        total_capacity = sum(int(event.capacity or 0) for event in events)
        slots_filled = int(row["slots_filled"])
        return {
            "capacity": total_capacity,
            "slots_filled": slots_filled,
            "slots_remaining": max(total_capacity - slots_filled, 0),
            "waitlist_length": int(row["waitlist_length"]),
            "capacity_override_count": int(row["capacity_override_count"]),
        }

    def _build_filtered_rows_query(self, filters: AnalyticsRegistrationQuery) -> Select[Any]:
        current_payment = aliased(Payment)
        batch_payment = aliased(Payment)
        latest_refund = self._latest_refund_request_subquery()

        payment_status_expression = case(
            (Registration.batch_id.is_not(None), batch_payment.status),
            else_=current_payment.status,
        )
        payment_reference_expression = case(
            (Registration.batch_id.is_not(None), batch_payment.payment_reference),
            else_=current_payment.payment_reference,
        )
        payment_gateway_expression = case(
            (Registration.batch_id.is_not(None), batch_payment.gateway),
            else_=current_payment.gateway,
        )
        paid_at_expression = case(
            (Registration.batch_id.is_not(None), batch_payment.paid_at),
            else_=current_payment.paid_at,
        )
        currency_expression = case(
            (Registration.batch_id.is_not(None), batch_payment.currency),
            else_=current_payment.currency,
        )

        # Batch payments are normalized to the per-participant seat price so that one shared
        # batch transaction does not get multiplied across analytics rows and exports.
        amount_paid_expression = case(
            (Event.is_free.is_(True), literal(0)),
            (ExceptionRegistrationOffer.payment_waived.is_(True), literal(0)),
            (Registration.batch_id.is_not(None), Event.price),
            (current_payment.amount.is_not(None), current_payment.amount),
            else_=Event.price,
        )

        query = (
            select(
                Registration.id.label("registration_id"),
                Registration.event_id.label("event_id"),
                Registration.batch_id.label("batch_id"),
                Registration.reg_id.label("reg_id"),
                Registration.first_name.label("first_name"),
                Registration.last_name.label("last_name"),
                Registration.email.label("email"),
                Registration.state.label("registration_state"),
                Registration.is_checked_in.label("is_checked_in"),
                Registration.checked_in_at.label("checked_in_at"),
                Registration.registered_at.label("registered_at"),
                Registration.was_waitlisted.label("was_waitlisted"),
                Registration.previous_waitlist_position.label("previous_waitlist_position"),
                Registration.cancellation_reason.label("cancellation_reason"),
                Event.title.label("event_title"),
                Event.event_date.label("event_date"),
                Event.location.label("event_location"),
                Event.is_free.label("event_is_free"),
                Event.capacity.label("event_capacity"),
                Event.price.label("event_price"),
                BatchRegistration.submitter_name.label("batch_submitter_name"),
                BatchRegistration.submitter_email.label("batch_submitter_email"),
                Registration.batch_id.is_not(None).label("is_batch"),
                latest_refund.c.refund_status.label("refund_status"),
                ExceptionRegistrationOffer.id.is_not(None).label("used_exception_offer"),
                func.coalesce(ExceptionRegistrationOffer.payment_waived, literal(False)).label("payment_waived"),
                func.coalesce(ExceptionRegistrationOffer.capacity_override, literal(False)).label(
                    "capacity_override_applied"
                ),
                payment_status_expression.label("payment_status"),
                payment_reference_expression.label("payment_reference"),
                payment_gateway_expression.label("payment_gateway"),
                paid_at_expression.label("paid_at"),
                func.coalesce(currency_expression, literal("NGN")).label("currency"),
                amount_paid_expression.label("amount_paid"),
            )
            .join(Event, Event.id == Registration.event_id)
            .outerjoin(BatchRegistration, BatchRegistration.id == Registration.batch_id)
            .outerjoin(current_payment, current_payment.id == Registration.current_payment_id)
            .outerjoin(batch_payment, batch_payment.batch_id == BatchRegistration.id)
            .outerjoin(latest_refund, latest_refund.c.registration_id == Registration.id)
            .outerjoin(
                ExceptionRegistrationOffer,
                ExceptionRegistrationOffer.used_registration_id == Registration.id,
            )
        )
        query = self._apply_filters(query, filters, amount_paid_expression, payment_status_expression, paid_at_expression)
        return query

    def _apply_filters(
        self,
        query: Select[Any],
        filters: AnalyticsRegistrationQuery,
        amount_paid_expression: Any,
        payment_status_expression: Any,
        paid_at_expression: Any,
    ) -> Select[Any]:
        if filters.event_ids:
            query = query.where(Registration.event_id.in_(filters.event_ids))
        if filters.date_from is not None:
            query = query.where(Registration.registered_at >= self._day_start(filters.date_from))
        if filters.date_to is not None:
            query = query.where(Registration.registered_at < self._day_end_exclusive(filters.date_to))
        if filters.state is not None:
            query = query.where(Registration.state == filters.state)
        if filters.is_checked_in is not None:
            query = query.where(Registration.is_checked_in.is_(filters.is_checked_in))
        if filters.email is not None:
            query = query.where(Registration.email.ilike(f"%{filters.email}%"))
        if filters.first_name is not None:
            query = query.where(Registration.first_name.ilike(f"%{filters.first_name}%"))
        if filters.last_name is not None:
            query = query.where(Registration.last_name.ilike(f"%{filters.last_name}%"))
        if filters.is_batch is not None:
            query = query.where(Registration.batch_id.is_not(None) if filters.is_batch else Registration.batch_id.is_(None))
        if filters.payment_status is not None:
            query = query.where(payment_status_expression == filters.payment_status)
        if filters.paid_from is not None:
            query = query.where(paid_at_expression >= self._day_start(filters.paid_from))
        if filters.paid_to is not None:
            query = query.where(paid_at_expression < self._day_end_exclusive(filters.paid_to))
        if filters.amount_min is not None:
            query = query.where(amount_paid_expression >= filters.amount_min)
        if filters.amount_max is not None:
            query = query.where(amount_paid_expression <= filters.amount_max)
        for custom_field_filter in filters.custom_field_filters:
            query = query.where(self._custom_field_filter_exists(custom_field_filter))
        return query

    def _apply_sorting(self, query: Select[Any], sort_by: str, sort_order: str) -> Select[Any]:
        descending = sort_order == "desc"
        if sort_by.startswith(CUSTOM_FIELD_SORT_PREFIX):
            field_definition_id = sort_by.removeprefix(CUSTOM_FIELD_SORT_PREFIX).strip()
            if not field_definition_id:
                raise ValidationError("custom field sorting requires a field_definition_id")
            sort_field_value = aliased(RegistrationFieldValue)
            query = query.outerjoin(
                sort_field_value,
                and_(
                    sort_field_value.registration_id == Registration.id,
                    sort_field_value.field_definition_id == field_definition_id,
                ),
            )
            ordering = sort_field_value.value.desc() if descending else sort_field_value.value.asc()
            return query.order_by(ordering.nulls_last(), Registration.registered_at.desc(), Registration.reg_id.asc())

        if sort_by not in SORTABLE_COLUMNS:
            raise ValidationError(f"Unsupported sort_by value '{sort_by}'.")

        sort_column = {
            "reg_id": Registration.reg_id,
            "first_name": Registration.first_name,
            "last_name": Registration.last_name,
            "email": Registration.email,
            "registration_state": Registration.state,
            "is_checked_in": Registration.is_checked_in,
            "checked_in_at": Registration.checked_in_at,
            "registered_at": Registration.registered_at,
            "is_batch": Registration.batch_id.is_not(None),
            "event_title": Event.title,
            "event_date": Event.event_date,
            "amount_paid": query.selected_columns.amount_paid,
            "payment_status": query.selected_columns.payment_status,
            "paid_at": query.selected_columns.paid_at,
        }[sort_by]
        ordered_column = sort_column.desc() if descending else sort_column.asc()
        return query.order_by(ordered_column.nulls_last(), Registration.registered_at.desc(), Registration.reg_id.asc())

    def _latest_refund_request_subquery(self) -> Any:
        ranked_refunds = (
            select(
                RefundRequest.registration_id.label("registration_id"),
                RefundRequest.status.label("refund_status"),
                func.row_number()
                .over(
                    partition_by=RefundRequest.registration_id,
                    order_by=(RefundRequest.requested_at.desc(), RefundRequest.id.desc()),
                )
                .label("row_number"),
            )
            .subquery()
        )
        return (
            select(
                ranked_refunds.c.registration_id,
                ranked_refunds.c.refund_status,
            )
            .where(ranked_refunds.c.row_number == 1)
            .subquery()
        )

    def _custom_field_filter_exists(self, custom_field_filter: AnalyticsCustomFieldFilter) -> Any:
        return exists(
            select(RegistrationFieldValue.id).where(
                RegistrationFieldValue.registration_id == Registration.id,
                RegistrationFieldValue.field_definition_id == custom_field_filter.field_definition_id,
                RegistrationFieldValue.value.ilike(f"%{custom_field_filter.value}%"),
            )
        )

    def _day_start(self, value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    def _day_end_exclusive(self, value: date) -> datetime:
        return datetime.combine(value + timedelta(days=1), time.min, tzinfo=timezone.utc)
