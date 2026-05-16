from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.event import EventState
from app.models.payment import PaymentStatus
from app.models.registration import RegistrationState
from app.models.staff import StaffAccessMode, StaffRole


EMAIL_REGEX = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    access_token_expires_in: int
    refresh_token_expires_in: int
    role: str


class RefreshAccessTokenRequest(BaseModel):
    refresh_token: str


class RefreshAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str
    access_token_expires_in: int


class StaffAccountSummary(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class StaffSelectedEventSummary(BaseModel):
    id: str
    title: str


class StaffAccountDetailResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    access_mode: StaffAccessMode
    selected_events: list[StaffSelectedEventSummary]


class StaffAccountUpdateRequest(BaseModel):
    email: str | None = None
    role: StaffRole | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not EMAIL_REGEX.fullmatch(stripped):
            raise ValueError("value is not a valid email address")
        return stripped

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "StaffAccountUpdateRequest":
        if self.email is None and self.role is None and self.is_active is None:
            raise ValueError("At least one field must be provided.")
        return self


class StaffAccessModeUpdateRequest(BaseModel):
    mode: StaffAccessMode


class StaffEventAccessAddRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=36)


class StaffAccessConfigResponse(BaseModel):
    staff_id: str
    access_mode: StaffAccessMode
    selected_events: list[StaffSelectedEventSummary]


class StaffRegistrationCustomFieldValueResponse(BaseModel):
    label: str
    value: str


class StaffRegistrationEventSummary(BaseModel):
    id: str
    title: str
    event_date: datetime
    location: str
    is_free: bool
    state: EventState


class StaffRegistrationPaymentSummary(BaseModel):
    status: PaymentStatus
    amount_paid: int
    currency: str
    paid_at: datetime | None


class StaffRegistrationResult(BaseModel):
    reg_id: str
    first_name: str
    last_name: str
    email: str
    state: RegistrationState
    is_checked_in: bool
    checked_in_at: datetime | None
    registered_at: datetime
    is_batch: bool
    custom_field_values: list[StaffRegistrationCustomFieldValueResponse]
    event: StaffRegistrationEventSummary
    payment: StaffRegistrationPaymentSummary | None


class StaffRegistrationSearchResponse(BaseModel):
    registrations: list[StaffRegistrationResult]
    total: int


class StaffRegistrationQueryParams(BaseModel):
    reg_id: str | None = None
    email: str | None = None

    @field_validator("reg_id")
    @classmethod
    def validate_reg_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not EMAIL_REGEX.fullmatch(stripped):
            raise ValueError("value is not a valid email address")
        return stripped

    @model_validator(mode="after")
    def validate_exactly_one_query(self) -> "StaffRegistrationQueryParams":
        if bool(self.reg_id) == bool(self.email):
            raise ValueError("Provide exactly one of reg_id or email.")
        return self


class StaffCheckInResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    is_checked_in: bool
    checked_in_at: datetime | None


class StaffNotificationResponse(BaseModel):
    id: str
    title: str
    body: str
    is_read: bool
    created_at: datetime


class StaffNotificationListResponse(BaseModel):
    notifications: list[StaffNotificationResponse]
    total: int


class StaffNotificationReadResponse(BaseModel):
    id: str
    is_read: bool
