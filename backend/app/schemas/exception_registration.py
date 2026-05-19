from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator

from app.models.exception_registration_offer import ExceptionRegistrationOfferStatus
from app.models.exception_registration_offer_audit import (
    ExceptionRegistrationOfferAuditAction,
    ExceptionRegistrationOfferAuditActorType,
)
from app.models.registration import RegistrationState
from app.schemas.registration import RegistrationCustomFieldValueInput


EMAIL_REGEX = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class ExceptionRegistrationOfferCreateRequest(BaseModel):
    target_email: str
    target_first_name: str | None = Field(default=None, min_length=1, max_length=120)
    target_last_name: str | None = Field(default=None, min_length=1, max_length=120)
    source_reg_id: str | None = Field(default=None, min_length=1, max_length=18)
    payment_waived: bool = False
    expires_at: datetime
    note: str | None = Field(default=None, min_length=1)

    @field_validator("target_email")
    @classmethod
    def validate_target_email(cls, value: str) -> str:
        stripped = value.strip()
        if not EMAIL_REGEX.fullmatch(stripped):
            raise ValueError("value is not a valid email address")
        return stripped

    @field_validator("target_first_name", "target_last_name", "source_reg_id", "note")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include timezone information.")
        return value


class ExceptionRegistrationOfferResponse(BaseModel):
    id: str
    event_id: str
    public_token: str
    registration_action_url: str
    target_email: str
    payment_waived: bool
    capacity_override: bool
    status: ExceptionRegistrationOfferStatus
    expires_at: datetime
    created_at: datetime


class ExceptionRegistrationOfferListResponse(BaseModel):
    event_id: str
    offers: list[ExceptionRegistrationOfferResponse]
    total: int


class ExceptionRegistrationOfferRevokeRequest(BaseModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class ExceptionRegistrationOfferRevokeResponse(BaseModel):
    id: str
    status: ExceptionRegistrationOfferStatus


class ExceptionRegistrationOfferAuditEntryResponse(BaseModel):
    action: ExceptionRegistrationOfferAuditAction
    actor_type: ExceptionRegistrationOfferAuditActorType
    actor_staff_id: str | None
    details: str | None
    created_at: datetime


class ExceptionRegistrationOfferAuditListResponse(BaseModel):
    offer_id: str
    entries: list[ExceptionRegistrationOfferAuditEntryResponse]


class ExceptionOfferRegistrationRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str
    custom_field_values: list[RegistrationCustomFieldValueInput] = Field(default_factory=list)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        stripped = value.strip()
        if not EMAIL_REGEX.fullmatch(stripped):
            raise ValueError("value is not a valid email address")
        return stripped


class ExceptionOfferRegistrationResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    payment_waived: bool
    payment_action_url: str | None
    message: str

