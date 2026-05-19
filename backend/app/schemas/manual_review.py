from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.manual_review_case import ManualReviewCaseStatus, ManualReviewCaseType
from app.models.registration import RegistrationState


class ManualReviewCaseResponse(BaseModel):
    id: str
    event_id: str | None
    registration_id: str | None
    reg_id: str | None
    payment_id: str | None
    payment_reference: str | None
    case_type: ManualReviewCaseType
    status: ManualReviewCaseStatus
    summary: str
    details: str | None
    created_by_system: bool
    created_by_staff_id: str | None
    assigned_to_staff_id: str | None
    resolved_by_staff_id: str | None
    resolution_action: str | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class ManualReviewCaseListResponse(BaseModel):
    cases: list[ManualReviewCaseResponse]
    total: int


class ManualReviewCaseUpdateRequest(BaseModel):
    status: ManualReviewCaseStatus
    resolution_action: str | None = Field(default=None, min_length=1, max_length=64)
    resolution_notes: str | None = Field(default=None, min_length=1)

    @field_validator("resolution_action", "resolution_notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @model_validator(mode="after")
    def validate_resolution_fields(self) -> "ManualReviewCaseUpdateRequest":
        if self.status in {ManualReviewCaseStatus.RESOLVED, ManualReviewCaseStatus.DISMISSED}:
            if self.resolution_notes is None:
                raise ValueError("resolution_notes is required when closing a manual review case.")
        return self


class RequeueRegistrationRequest(BaseModel):
    reason: str = Field(min_length=1)
    notify_user: bool = False

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be empty")
        return stripped


class RequeueRegistrationResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    manual_review_case_id: str
    message: str


class RegistrationPaymentInitializationResponse(BaseModel):
    checkout_url: str
    payment_reference: str
    message: str
