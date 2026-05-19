from __future__ import annotations

from datetime import date, datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.payment import PaymentGateway, PaymentStatus
from app.models.refund_request import RefundRequestStatus
from app.models.registration import CancellationReason, RegistrationState


CUSTOM_FIELD_FILTER_PATTERN = re.compile(r"^(?P<field_id>[^:]+):(?P<value>.+)$")


class AnalyticsCustomFieldFilter(BaseModel):
    field_definition_id: str = Field(min_length=1, max_length=36)
    value: str = Field(min_length=1)

    @field_validator("field_definition_id", "value")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class AnalyticsEventReference(BaseModel):
    id: str
    title: str


class AnalyticsDateRangeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date | None = Field(alias="from")
    to: date | None = None


class AnalyticsRegistrationSummaryResponse(BaseModel):
    total_registrations: int
    confirmed: int
    cancelled: int
    waitlisted: int
    refunded: int
    failed: int
    checked_in_count: int
    check_in_rate: str


class AnalyticsRevenueByEventResponse(BaseModel):
    event_id: str
    title: str
    gross_revenue: int


class AnalyticsRevenueResponse(BaseModel):
    gross_revenue: int
    net_revenue: int
    total_refunded: int
    average_ticket_price: int
    currency: str = "NGN"
    revenue_by_event: list[AnalyticsRevenueByEventResponse]


class AnalyticsTrendPointResponse(BaseModel):
    date: date
    count: int
    cumulative: int


class AnalyticsRegistrationTrendsResponse(BaseModel):
    peak_registration_day: date | None
    daily: list[AnalyticsTrendPointResponse]


class AnalyticsBatchVsSingleResponse(BaseModel):
    single_registration_count: int
    batch_registration_count: int
    batch_submission_count: int
    average_batch_size: float


class AnalyticsCapacityResponse(BaseModel):
    capacity: int
    slots_filled: int
    slots_remaining: int
    waitlist_length: int
    fill_rate: str
    capacity_override_count: int


class AnalyticsResponse(BaseModel):
    events: list[AnalyticsEventReference]
    date_range: AnalyticsDateRangeResponse
    registration_summary: AnalyticsRegistrationSummaryResponse
    revenue: AnalyticsRevenueResponse
    registration_trends: AnalyticsRegistrationTrendsResponse
    batch_vs_single: AnalyticsBatchVsSingleResponse
    capacity: AnalyticsCapacityResponse | None = None


class AnalyticsRegistrationCustomFieldResponse(BaseModel):
    label: str
    value: str


class AnalyticsRegistrationEventResponse(BaseModel):
    id: str
    title: str
    event_date: datetime
    location: str
    is_free: bool


class AnalyticsRegistrationPaymentResponse(BaseModel):
    amount_paid: int
    currency: str
    payment_gateway: PaymentGateway | None
    payment_reference: str | None
    payment_status: PaymentStatus | None
    paid_at: datetime | None


class AnalyticsRegistrationRowResponse(BaseModel):
    reg_id: str
    first_name: str
    last_name: str
    email: str
    registration_state: RegistrationState
    refund_status: RefundRequestStatus | None = None
    cancellation_reason: CancellationReason | None = None
    was_waitlisted: bool
    previous_waitlist_position: int | None = None
    is_checked_in: bool
    checked_in_at: datetime | None = None
    registered_at: datetime
    is_batch: bool
    batch_submitter_name: str | None = None
    batch_submitter_email: str | None = None
    used_exception_offer: bool
    payment_waived: bool
    capacity_override_applied: bool
    event: AnalyticsRegistrationEventResponse
    payment: AnalyticsRegistrationPaymentResponse | None = None
    custom_fields: list[AnalyticsRegistrationCustomFieldResponse]


class AnalyticsRegistrationsResponse(BaseModel):
    page: int
    page_size: int
    total: int
    sort_by: str
    sort_order: str
    registrations: list[AnalyticsRegistrationRowResponse]


class AnalyticsRegistrationQuery(BaseModel):
    event_ids: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    state: RegistrationState | None = None
    is_checked_in: bool | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_batch: bool | None = None
    payment_status: PaymentStatus | None = None
    paid_from: date | None = None
    paid_to: date | None = None
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    custom_field_filters: list[AnalyticsCustomFieldFilter] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort_by: str = "registered_at"
    sort_order: str = "desc"

    @field_validator("email", "first_name", "last_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, value: str) -> str:
        lowered = value.strip().lower()
        if lowered not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return lowered

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("sort_by must not be empty")
        return stripped

    @field_validator("event_ids")
    @classmethod
    def strip_event_ids(cls, values: list[str]) -> list[str]:
        stripped_values = [value.strip() for value in values if value.strip()]
        if len(stripped_values) != len(set(stripped_values)):
            raise ValueError("event_ids must be unique")
        return stripped_values

    @model_validator(mode="after")
    def validate_ranges(self) -> "AnalyticsRegistrationQuery":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if self.paid_from is not None and self.paid_to is not None and self.paid_from > self.paid_to:
            raise ValueError("paid_from must be on or before paid_to")
        if self.amount_min is not None and self.amount_max is not None and self.amount_min > self.amount_max:
            raise ValueError("amount_min must be less than or equal to amount_max")
        return self

    @classmethod
    def parse_custom_field_filters(cls, raw_filters: list[str]) -> list[AnalyticsCustomFieldFilter]:
        parsed_filters: list[AnalyticsCustomFieldFilter] = []
        for raw_filter in raw_filters:
            match = CUSTOM_FIELD_FILTER_PATTERN.fullmatch(raw_filter.strip())
            if match is None:
                raise ValueError("custom_field filters must use the format '<field_definition_id>:<value>'")
            parsed_filters.append(
                AnalyticsCustomFieldFilter(
                    field_definition_id=match.group("field_id"),
                    value=match.group("value"),
                )
            )
        return parsed_filters


class AnalyticsDownloadFormat(str):
    CSV = "csv"
    PDF = "pdf"


class AnalyticsDownloadQuery(AnalyticsRegistrationQuery):
    format: str

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        lowered = value.strip().lower()
        if lowered not in {AnalyticsDownloadFormat.CSV, AnalyticsDownloadFormat.PDF}:
            raise ValueError("format must be 'csv' or 'pdf'")
        return lowered
