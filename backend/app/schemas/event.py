from __future__ import annotations

from datetime import datetime
import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.models.event import EventState, FieldType, OverflowRule


PREFIX_PATTERN = r"^[A-Z0-9]{2,5}$"
PREFIX_ERROR_MESSAGE = "prefix must be 2-5 uppercase alphanumeric characters"


class EventCustomFieldInput(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    field_type: FieldType
    is_required: bool = False
    display_order: int = Field(gt=0)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        label = value.strip()
        if not label:
            raise PydanticCustomError("value_error", "label must not be empty")
        return label


class EventCustomFieldResponse(EventCustomFieldInput):
    id: str

    model_config = ConfigDict(from_attributes=True)


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    event_date: datetime
    location: str = Field(min_length=1, max_length=255)
    prefix: str
    price: int = Field(ge=0)
    capacity: int | None = Field(default=None, gt=0)
    overflow_rule: OverflowRule = OverflowRule.HARD_REJECTION
    custom_fields: list[EventCustomFieldInput] = Field(default_factory=list)

    @field_validator("title", "description", "location")
    @classmethod
    def strip_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not re.fullmatch(PREFIX_PATTERN, value):
            raise PydanticCustomError("value_error", PREFIX_ERROR_MESSAGE)
        return value

    @model_validator(mode="after")
    def validate_custom_field_order(self) -> Self:
        display_orders = [field.display_order for field in self.custom_fields]
        if len(display_orders) != len(set(display_orders)):
            raise PydanticCustomError("value_error", "custom_fields display_order values must be unique")
        return self


class EventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    event_date: datetime | None = None
    location: str | None = Field(default=None, min_length=1, max_length=255)
    prefix: str | None = None
    price: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, gt=0)
    overflow_rule: OverflowRule | None = None
    custom_fields: list[EventCustomFieldInput] | None = None

    @field_validator("title", "description", "location")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("prefix")
    @classmethod
    def validate_optional_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(PREFIX_PATTERN, value):
            raise PydanticCustomError("value_error", PREFIX_ERROR_MESSAGE)
        return value

    @model_validator(mode="after")
    def validate_custom_field_order(self) -> Self:
        if self.custom_fields is None:
            return self
        display_orders = [field.display_order for field in self.custom_fields]
        if len(display_orders) != len(set(display_orders)):
            raise PydanticCustomError("value_error", "custom_fields display_order values must be unique")
        return self


class EventStateUpdateRequest(BaseModel):
    state: EventState


class PublicEventSummaryResponse(BaseModel):
    id: str
    title: str
    description: str
    event_date: datetime
    location: str
    price: int
    is_free: bool
    state: EventState
    capacity: int | None
    slots_remaining: int | None


class PublicEventListResponse(BaseModel):
    events: list[PublicEventSummaryResponse]
    total: int


class PublicEventDetailResponse(PublicEventSummaryResponse):
    custom_fields: list[EventCustomFieldResponse]


class EventRegistrationCountsResponse(BaseModel):
    total_registrations: int
    pending_payment: int
    confirmed: int
    failed: int
    cancelled: int
    refund_requested: int
    refunded: int
    waitlisted: int


class AdminEventSummaryResponse(BaseModel):
    id: str
    title: str
    description: str
    event_date: datetime
    location: str
    prefix: str
    price: int
    is_free: bool
    capacity: int | None
    overflow_rule: OverflowRule
    state: EventState
    registration_count: int
    confirmed_count: int
    slots_remaining: int | None
    created_at: datetime
    updated_at: datetime


class AdminEventListResponse(BaseModel):
    events: list[AdminEventSummaryResponse]
    total: int


class AdminEventDetailResponse(BaseModel):
    id: str
    title: str
    description: str
    event_date: datetime
    location: str
    prefix: str
    price: int
    is_free: bool
    capacity: int | None
    overflow_rule: OverflowRule
    state: EventState
    slots_remaining: int | None
    custom_fields: list[EventCustomFieldResponse]
    registration_counts: EventRegistrationCountsResponse
    created_at: datetime
    updated_at: datetime
