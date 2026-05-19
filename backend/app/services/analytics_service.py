from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import os
import tempfile

from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    AnalyticsBatchVsSingleResponse,
    AnalyticsCapacityResponse,
    AnalyticsDateRangeResponse,
    AnalyticsDownloadFormat,
    AnalyticsDownloadQuery,
    AnalyticsEventReference,
    AnalyticsRegistrationCustomFieldResponse,
    AnalyticsRegistrationEventResponse,
    AnalyticsRegistrationPaymentResponse,
    AnalyticsRegistrationQuery,
    AnalyticsRegistrationRowResponse,
    AnalyticsRegistrationsResponse,
    AnalyticsRegistrationSummaryResponse,
    AnalyticsRegistrationTrendsResponse,
    AnalyticsResponse,
    AnalyticsRevenueByEventResponse,
    AnalyticsRevenueResponse,
    AnalyticsTrendPointResponse,
)
from app.utils.csv_generator import build_csv_writer, build_download_headers, build_download_row
from app.utils.pdf_generator import AnalyticsPdfWriter


DOWNLOAD_CHUNK_SIZE = 200


@dataclass(frozen=True)
class AnalyticsDownloadArtifact:
    path: str
    filename: str
    media_type: str


@dataclass
class AnalyticsService:
    session: object

    def __post_init__(self) -> None:
        self.repository = AnalyticsRepository(self.session)

    async def get_analytics(self, filters: AnalyticsRegistrationQuery) -> AnalyticsResponse:
        events = await self.repository.list_events_in_scope(filters.event_ids)
        summary_metrics = await self.repository.get_registration_summary_metrics(filters)
        revenue_metrics = await self.repository.get_revenue_metrics(filters)
        batch_metrics = await self.repository.get_batch_metrics(filters)
        trend_counts = await self.repository.get_registration_trend_counts(filters)

        # Refunds moved into a dedicated refund_requests workflow in Phase 13.5A.3,
        # so refunded metrics are derived from refund status rather than registration state.
        registration_summary = AnalyticsRegistrationSummaryResponse(
            total_registrations=summary_metrics["total_registrations"],
            confirmed=summary_metrics["confirmed"],
            cancelled=summary_metrics["cancelled"],
            waitlisted=summary_metrics["waitlisted"],
            refunded=summary_metrics["refunded"],
            failed=summary_metrics["failed"],
            checked_in_count=summary_metrics["checked_in_count"],
            check_in_rate=self._format_percentage(
                summary_metrics["checked_in_count"],
                summary_metrics["confirmed"],
            ),
        )
        revenue = AnalyticsRevenueResponse(
            gross_revenue=revenue_metrics["gross_revenue"],
            net_revenue=revenue_metrics["net_revenue"],
            total_refunded=revenue_metrics["total_refunded"],
            average_ticket_price=(
                revenue_metrics["gross_revenue"] // summary_metrics["confirmed"]
                if summary_metrics["confirmed"] > 0
                else 0
            ),
            revenue_by_event=[
                AnalyticsRevenueByEventResponse(
                    event_id=row.event_id,
                    title=row.title,
                    gross_revenue=row.gross_revenue,
                )
                for row in revenue_metrics["revenue_by_event"]
            ],
        )
        trends = AnalyticsRegistrationTrendsResponse(
            peak_registration_day=self._determine_peak_registration_day(trend_counts),
            daily=self._build_daily_trends(
                trend_counts=trend_counts,
                events=events,
                date_from=filters.date_from,
                date_to=filters.date_to,
            ),
        )
        batch_vs_single = AnalyticsBatchVsSingleResponse(
            single_registration_count=int(batch_metrics["single_registration_count"]),
            batch_registration_count=int(batch_metrics["batch_registration_count"]),
            batch_submission_count=int(batch_metrics["batch_submission_count"]),
            average_batch_size=float(batch_metrics["average_batch_size"]),
        )

        # The operational capacity model counts confirmed and pending_payment as slot-consuming.
        # This intentionally differs from the older pre-13.5A confirmed-only assumption.
        capacity_metrics = await self.repository.get_capacity_metrics(filters, events)
        capacity = None
        if capacity_metrics is not None:
            capacity = AnalyticsCapacityResponse(
                capacity=capacity_metrics["capacity"],
                slots_filled=capacity_metrics["slots_filled"],
                slots_remaining=capacity_metrics["slots_remaining"],
                waitlist_length=capacity_metrics["waitlist_length"],
                fill_rate=self._format_percentage(
                    capacity_metrics["slots_filled"],
                    capacity_metrics["capacity"],
                ),
                capacity_override_count=capacity_metrics["capacity_override_count"],
            )

        return AnalyticsResponse(
            events=[AnalyticsEventReference(id=event.id, title=event.title) for event in events],
            date_range=AnalyticsDateRangeResponse(from_=filters.date_from, to=filters.date_to),
            registration_summary=registration_summary,
            revenue=revenue,
            registration_trends=trends,
            batch_vs_single=batch_vs_single,
            capacity=capacity,
        )

    async def get_registration_table(self, filters: AnalyticsRegistrationQuery) -> AnalyticsRegistrationsResponse:
        total = await self.repository.count_filtered_registrations(filters)
        rows = await self.repository.list_filtered_registration_rows(filters)
        custom_field_values = await self.repository.list_custom_field_values(
            [str(row["registration_id"]) for row in rows]
        )
        registrations = [
            self._build_registration_row_response(
                row,
                custom_field_values.get(str(row["registration_id"]), []),
            )
            for row in rows
        ]
        return AnalyticsRegistrationsResponse(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            sort_by=filters.sort_by,
            sort_order=filters.sort_order,
            registrations=registrations,
        )

    async def build_download(self, filters: AnalyticsDownloadQuery) -> AnalyticsDownloadArtifact:
        custom_field_labels = await self.repository.list_custom_field_labels(filters)
        if filters.format == AnalyticsDownloadFormat.CSV:
            path = self._allocate_temp_path(".csv")
            await self._write_csv_download(path, filters, custom_field_labels)
            return AnalyticsDownloadArtifact(
                path=path,
                filename=self._build_download_filename("csv"),
                media_type="text/csv; charset=utf-8",
            )

        path = self._allocate_temp_path(".pdf")
        analytics = await self.get_analytics(filters)
        await self._write_pdf_download(path, filters, analytics, custom_field_labels)
        return AnalyticsDownloadArtifact(
            path=path,
            filename=self._build_download_filename("pdf"),
            media_type="application/pdf",
        )

    async def _write_csv_download(
        self,
        path: str,
        filters: AnalyticsRegistrationQuery,
        custom_field_labels: list[str],
    ) -> None:
        with open(path, "w", encoding="utf-8", newline="") as file_obj:
            writer = build_csv_writer(file_obj, custom_field_labels)
            async for registration in self._iter_registration_rows(filters):
                writer.writerow(build_download_row(registration, custom_field_labels))

    async def _write_pdf_download(
        self,
        path: str,
        filters: AnalyticsRegistrationQuery,
        analytics: AnalyticsResponse,
        custom_field_labels: list[str],
    ) -> None:
        event_label = analytics.events[0].title if len(analytics.events) == 1 else "Multiple Events"
        event_date_label = "Multiple Dates"
        if len(analytics.events) == 1 and analytics.events:
            event_scope = await self.repository.list_events_in_scope([analytics.events[0].id])
            if event_scope:
                event_date_label = event_scope[0].event_date.isoformat().replace("+00:00", "Z")

        writer = AnalyticsPdfWriter(
            path=path,
            event_label=event_label,
            event_date_label=event_date_label,
            total_records=analytics.registration_summary.total_registrations,
            total_confirmed=analytics.registration_summary.confirmed,
            gross_revenue=analytics.revenue.gross_revenue,
            check_in_rate=analytics.registration_summary.check_in_rate,
            columns=build_download_headers(custom_field_labels),
        )
        async for registration in self._iter_registration_rows(filters):
            writer.write_row(build_download_row(registration, custom_field_labels))
        writer.save()

    async def _iter_registration_rows(
        self,
        filters: AnalyticsRegistrationQuery,
    ):
        page = 1
        while True:
            page_filters = filters.model_copy(update={"page": page, "page_size": DOWNLOAD_CHUNK_SIZE})
            rows = await self.repository.list_filtered_registration_rows(page_filters)
            if not rows:
                break
            custom_field_values = await self.repository.list_custom_field_values(
                [str(row["registration_id"]) for row in rows]
            )
            for row in rows:
                yield self._build_registration_row_response(
                    row,
                    custom_field_values.get(str(row["registration_id"]), []),
                )
            page += 1

    def _build_registration_row_response(
        self,
        row: dict,
        custom_fields: list[dict[str, str]],
    ) -> AnalyticsRegistrationRowResponse:
        payment = None
        if not row["event_is_free"]:
            payment = AnalyticsRegistrationPaymentResponse(
                amount_paid=int(row["amount_paid"]),
                currency=str(row["currency"] or "NGN"),
                payment_gateway=row["payment_gateway"],
                payment_reference=row["payment_reference"],
                payment_status=row["payment_status"],
                paid_at=row["paid_at"],
            )

        return AnalyticsRegistrationRowResponse(
            reg_id=str(row["reg_id"]),
            first_name=str(row["first_name"]),
            last_name=str(row["last_name"]),
            email=str(row["email"]),
            registration_state=row["registration_state"],
            refund_status=row["refund_status"],
            cancellation_reason=row["cancellation_reason"],
            was_waitlisted=bool(row["was_waitlisted"]),
            previous_waitlist_position=row["previous_waitlist_position"],
            is_checked_in=bool(row["is_checked_in"]),
            checked_in_at=row["checked_in_at"],
            registered_at=row["registered_at"],
            is_batch=bool(row["is_batch"]),
            batch_submitter_name=row["batch_submitter_name"],
            batch_submitter_email=row["batch_submitter_email"],
            used_exception_offer=bool(row["used_exception_offer"]),
            payment_waived=bool(row["payment_waived"]),
            capacity_override_applied=bool(row["capacity_override_applied"]),
            event=AnalyticsRegistrationEventResponse(
                id=str(row["event_id"]),
                title=str(row["event_title"]),
                event_date=row["event_date"],
                location=str(row["event_location"]),
                is_free=bool(row["event_is_free"]),
            ),
            payment=payment,
            custom_fields=[
                AnalyticsRegistrationCustomFieldResponse(label=item["label"], value=item["value"])
                for item in custom_fields
            ],
        )

    def _build_daily_trends(
        self,
        *,
        trend_counts,
        events,
        date_from: date | None,
        date_to: date | None,
    ) -> list[AnalyticsTrendPointResponse]:
        if not events:
            return []
        start_date = date_from or min(event.created_at.date() for event in events)
        end_date = date_to or max(event.event_date.date() for event in events)
        counts_by_date = {trend.point_date: trend.count for trend in trend_counts}
        daily_points: list[AnalyticsTrendPointResponse] = []
        cumulative = 0
        current_date = start_date
        while current_date <= end_date:
            count = counts_by_date.get(current_date, 0)
            cumulative += count
            daily_points.append(
                AnalyticsTrendPointResponse(date=current_date, count=count, cumulative=cumulative)
            )
            current_date += timedelta(days=1)
        return daily_points

    def _determine_peak_registration_day(self, trend_counts) -> date | None:
        if not trend_counts:
            return None
        peak = max(trend_counts, key=lambda trend: (trend.count, -trend.point_date.toordinal()))
        return peak.point_date

    def _format_percentage(self, numerator: int, denominator: int) -> str:
        if denominator <= 0:
            return "0.00%"
        return f"{(numerator / denominator) * 100:.2f}%"

    def _allocate_temp_path(self, suffix: str) -> str:
        fd, path = tempfile.mkstemp(prefix="analytics_", suffix=suffix)
        os.close(fd)
        return path

    def _build_download_filename(self, extension: str) -> str:
        return f"analytics-download.{extension}"
