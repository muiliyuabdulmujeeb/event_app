from __future__ import annotations

from collections.abc import Iterator
from datetime import date
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, require_admin
from app.core.exceptions import AppError, as_http_exception
from app.models.payment import PaymentStatus
from app.models.registration import RegistrationState
from app.models.staff import StaffAccount
from app.schemas.analytics import AnalyticsDownloadQuery, AnalyticsRegistrationQuery, AnalyticsRegistrationsResponse, AnalyticsResponse
from app.services.analytics_service import AnalyticsService


router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("", response_model=AnalyticsResponse, response_model_exclude_none=True)
async def get_analytics(
    _: Annotated[StaffAccount, Depends(require_admin)],
    filters: Annotated[AnalyticsRegistrationQuery, Depends(_build_analytics_query)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AnalyticsResponse:
    service = AnalyticsService(session=session)
    try:
        return await service.get_analytics(filters)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get("/registrations", response_model=AnalyticsRegistrationsResponse)
async def get_registration_table(
    _: Annotated[StaffAccount, Depends(require_admin)],
    filters: Annotated[AnalyticsRegistrationQuery, Depends(_build_registration_query)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AnalyticsRegistrationsResponse:
    service = AnalyticsService(session=session)
    try:
        return await service.get_registration_table(filters)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get("/download", status_code=status.HTTP_200_OK)
async def download_analytics(
    _: Annotated[StaffAccount, Depends(require_admin)],
    filters: Annotated[AnalyticsDownloadQuery, Depends(_build_download_query)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    service = AnalyticsService(session=session)
    try:
        artifact = await service.build_download(filters)
    except AppError as exc:
        raise as_http_exception(exc) from exc

    headers = {"Content-Disposition": f'attachment; filename="{artifact.filename}"'}
    return StreamingResponse(
        _stream_file_and_delete(artifact.path),
        media_type=artifact.media_type,
        headers=headers,
    )


def _stream_file_and_delete(path: str) -> Iterator[bytes]:
    try:
        with open(path, "rb") as file_obj:
            while chunk := file_obj.read(8192):
                yield chunk
    finally:
        if os.path.exists(path):
            os.remove(path)


def _build_analytics_query(
    event_ids: Annotated[list[str], Query()] = [],
    date_from: date | None = None,
    date_to: date | None = None,
) -> AnalyticsRegistrationQuery:
    return _validate_query_model(
        AnalyticsRegistrationQuery,
        {
            "event_ids": event_ids,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


def _build_registration_query(
    event_ids: Annotated[list[str], Query()] = [],
    date_from: date | None = None,
    date_to: date | None = None,
    state: RegistrationState | None = None,
    is_checked_in: bool | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    is_batch: bool | None = None,
    payment_status: PaymentStatus | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    amount_min: int | None = Query(default=None, ge=0),
    amount_max: int | None = Query(default=None, ge=0),
    custom_field: Annotated[list[str], Query()] = [],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = "registered_at",
    sort_order: str = "desc",
) -> AnalyticsRegistrationQuery:
    try:
        custom_field_filters = AnalyticsRegistrationQuery.parse_custom_field_filters(custom_field)
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "custom_field"), "msg": str(exc), "type": "value_error"}]
        ) from exc
    return _validate_query_model(
        AnalyticsRegistrationQuery,
        {
            "event_ids": event_ids,
            "date_from": date_from,
            "date_to": date_to,
            "state": state,
            "is_checked_in": is_checked_in,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_batch": is_batch,
            "payment_status": payment_status,
            "paid_from": paid_from,
            "paid_to": paid_to,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "custom_field_filters": custom_field_filters,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


def _build_download_query(
    format: str,
    event_ids: Annotated[list[str], Query()] = [],
    date_from: date | None = None,
    date_to: date | None = None,
    state: RegistrationState | None = None,
    is_checked_in: bool | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    is_batch: bool | None = None,
    payment_status: PaymentStatus | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    amount_min: int | None = Query(default=None, ge=0),
    amount_max: int | None = Query(default=None, ge=0),
    custom_field: Annotated[list[str], Query()] = [],
    sort_by: str = "registered_at",
    sort_order: str = "desc",
) -> AnalyticsDownloadQuery:
    try:
        custom_field_filters = AnalyticsRegistrationQuery.parse_custom_field_filters(custom_field)
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "custom_field"), "msg": str(exc), "type": "value_error"}]
        ) from exc
    return _validate_query_model(
        AnalyticsDownloadQuery,
        {
            "format": format,
            "event_ids": event_ids,
            "date_from": date_from,
            "date_to": date_to,
            "state": state,
            "is_checked_in": is_checked_in,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_batch": is_batch,
            "payment_status": payment_status,
            "paid_from": paid_from,
            "paid_to": paid_to,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "custom_field_filters": custom_field_filters,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


def _validate_query_model(model, payload):
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
