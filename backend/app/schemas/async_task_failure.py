from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.async_task_failure import AsyncTaskFailureStatus, AsyncTaskType


class AsyncTaskFailureUpdateRequest(BaseModel):
    status: AsyncTaskFailureStatus
    resolution_notes: str | None = None


class AsyncTaskFailureResponse(BaseModel):
    id: str
    task_name: str
    task_type: AsyncTaskType
    failure_category: str
    status: AsyncTaskFailureStatus
    event_id: str | None
    registration_id: str | None
    reg_id: str | None
    payment_id: str | None
    payment_reference: str | None
    acknowledged_by_staff_id: str | None
    acknowledged_at: datetime | None
    resolved_by_staff_id: str | None
    resolved_at: datetime | None
    resolution_notes: str | None
    provider_attempts: list[dict[str, Any]] | None
    attempt_count: int
    error_class: str
    error_message: str
    payload_metadata: dict[str, Any] | None
    final_failed_at: datetime
    created_at: datetime
    updated_at: datetime


class AsyncTaskFailureListResponse(BaseModel):
    failures: list[AsyncTaskFailureResponse]
    total: int
