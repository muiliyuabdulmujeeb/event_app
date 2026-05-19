from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.refund_request import RefundRequestStatus
from app.models.registration import CancellationReason, RegistrationState
from app.schemas.notification import NotificationMethod


class RegistrationCancellationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_optional_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class RegistrationCancellationResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    was_waitlisted: bool
    previous_waitlist_position: int | None
    cancellation_reason: CancellationReason | None
    message: str


class RefundRequestCreateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_optional_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class RefundRequestCreateResponse(BaseModel):
    refund_request_id: str
    reg_id: str
    status: RefundRequestStatus
    requested_at: datetime
    message: str


class AdminRefundRequestSummaryResponse(BaseModel):
    refund_request_id: str
    reg_id: str
    status: RefundRequestStatus
    requested_at: datetime
    processed_at: datetime | None


class AdminRefundRequestListResponse(BaseModel):
    items: list[AdminRefundRequestSummaryResponse]
    total: int


class AdminRefundRequestUpdateRequest(BaseModel):
    status: RefundRequestStatus
    notification_method: NotificationMethod
    message_body: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    resolution_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("message_body", "title", "resolution_notes")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("status")
    @classmethod
    def validate_non_requested_status(cls, value: RefundRequestStatus) -> RefundRequestStatus:
        if value == RefundRequestStatus.REQUESTED:
            raise ValueError("status must not be requested")
        return value


class AdminRefundRequestUpdateResponse(BaseModel):
    refund_request_id: str
    reg_id: str
    status: RefundRequestStatus
    processed_at: datetime | None
    message: str
