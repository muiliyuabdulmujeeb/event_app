from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_current_account, get_db_session
from app.core.exceptions import AppError, as_http_exception
from app.models.async_task_failure import AsyncTaskFailureStatus, AsyncTaskType
from app.models.manual_review_case import ManualReviewCaseStatus, ManualReviewCaseType
from app.models.staff import StaffAccount
from app.repositories.async_task_failure_repository import AsyncTaskFailureFilters
from app.repositories.manual_review_repository import ManualReviewCaseFilters
from app.schemas.async_task_failure import AsyncTaskFailureListResponse, AsyncTaskFailureResponse
from app.schemas.async_task_failure import AsyncTaskFailureUpdateRequest
from app.schemas.staff import (
    StaffCheckInResponse,
    StaffNotificationListResponse,
    StaffNotificationReadResponse,
    StaffRegistrationSearchResponse,
)
from app.schemas.manual_review import (
    ManualReviewCaseListResponse,
    ManualReviewCaseResponse,
    ManualReviewCaseUpdateRequest,
    RequeueRegistrationRequest,
    RequeueRegistrationResponse,
)
from app.schemas.waitlist_promotion import WaitlistPromotionRequest, WaitlistPromotionResponse
from app.services.async_task_failure_service import AsyncTaskFailureService
from app.services.email_service import EmailService
from app.services.manual_review_service import ManualReviewService
from app.services.staff_service import StaffService
from app.services.waitlist_promotion_service import WaitlistPromotionService


router = APIRouter(prefix="/staff", tags=["staff"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("/registrations", response_model=StaffRegistrationSearchResponse)
async def search_registrations(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    reg_id: Annotated[str | None, Query()] = None,
    email: Annotated[str | None, Query()] = None,
) -> StaffRegistrationSearchResponse:
    service = StaffService(session=session)
    try:
        return await service.search_registrations(actor=account, reg_id=reg_id, email=email)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/checkin", response_model=StaffCheckInResponse, status_code=status.HTTP_200_OK)
async def check_in_registration(
    reg_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffCheckInResponse:
    service = StaffService(session=session)
    try:
        response = await service.check_in_registration(actor=account, reg_id=reg_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/uncheckin", response_model=StaffCheckInResponse, status_code=status.HTTP_200_OK)
async def uncheck_in_registration(
    reg_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffCheckInResponse:
    service = StaffService(session=session)
    try:
        response = await service.uncheck_in_registration(actor=account, reg_id=reg_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/promote", response_model=WaitlistPromotionResponse, status_code=status.HTTP_200_OK)
async def promote_waitlisted_registration(
    reg_id: str,
    payload: WaitlistPromotionRequest,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> WaitlistPromotionResponse:
    service = WaitlistPromotionService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.promote_waitlisted_registration(actor=account, reg_id=reg_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.get("/notifications", response_model=StaffNotificationListResponse)
async def list_staff_notifications(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffNotificationListResponse:
    service = StaffService(session=session)
    try:
        return await service.list_unread_notifications(actor=account)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get("/dead-letters", response_model=AsyncTaskFailureListResponse)
async def list_async_task_failures(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    task_type: Annotated[AsyncTaskType | None, Query()] = None,
    status: Annotated[AsyncTaskFailureStatus | None, Query()] = None,
    event_id: Annotated[str | None, Query()] = None,
    registration_id: Annotated[str | None, Query()] = None,
    payment_id: Annotated[str | None, Query()] = None,
) -> AsyncTaskFailureListResponse:
    service = AsyncTaskFailureService(session=session)
    try:
        return await service.list_failures(
            actor=account,
            filters=AsyncTaskFailureFilters(
                task_type=task_type,
                status=status,
                event_id=event_id,
                registration_id=registration_id,
                payment_id=payment_id,
            ),
        )
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get("/dead-letters/{dead_letter_id}", response_model=AsyncTaskFailureResponse)
async def get_async_task_failure(
    dead_letter_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncTaskFailureResponse:
    service = AsyncTaskFailureService(session=session)
    try:
        return await service.get_failure(actor=account, failure_id=dead_letter_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/dead-letters/{dead_letter_id}", response_model=AsyncTaskFailureResponse, status_code=status.HTTP_200_OK)
async def update_async_task_failure(
    dead_letter_id: str,
    payload: AsyncTaskFailureUpdateRequest,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncTaskFailureResponse:
    service = AsyncTaskFailureService(session=session)
    try:
        response = await service.update_failure(actor=account, failure_id=dead_letter_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/notifications/{notification_id}/read", response_model=StaffNotificationReadResponse, status_code=status.HTTP_200_OK)
async def mark_staff_notification_read(
    notification_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StaffNotificationReadResponse:
    service = StaffService(session=session)
    try:
        response = await service.mark_notification_read(actor=account, notification_id=notification_id)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.get("/manual-reviews", response_model=ManualReviewCaseListResponse)
async def list_manual_review_cases(
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    status: Annotated[ManualReviewCaseStatus | None, Query()] = None,
    case_type: Annotated[ManualReviewCaseType | None, Query()] = None,
    event_id: Annotated[str | None, Query()] = None,
    registration_id: Annotated[str | None, Query()] = None,
    payment_id: Annotated[str | None, Query()] = None,
) -> ManualReviewCaseListResponse:
    service = ManualReviewService(session=session, settings=settings)
    try:
        return await service.list_cases(
            actor=account,
            filters=ManualReviewCaseFilters(
                status=status,
                case_type=case_type,
                event_id=event_id,
                registration_id=registration_id,
                payment_id=payment_id,
            ),
        )
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get("/manual-reviews/{case_id}", response_model=ManualReviewCaseResponse)
async def get_manual_review_case(
    case_id: str,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ManualReviewCaseResponse:
    service = ManualReviewService(session=session, settings=settings)
    try:
        return await service.get_case(actor=account, case_id=case_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/manual-reviews/{case_id}", response_model=ManualReviewCaseResponse, status_code=status.HTTP_200_OK)
async def update_manual_review_case(
    case_id: str,
    payload: ManualReviewCaseUpdateRequest,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ManualReviewCaseResponse:
    service = ManualReviewService(session=session, settings=settings)
    try:
        response = await service.update_case(actor=account, case_id=case_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/registrations/{reg_id}/requeue", response_model=RequeueRegistrationResponse, status_code=status.HTTP_200_OK)
async def requeue_registration(
    reg_id: str,
    payload: RequeueRegistrationRequest,
    account: Annotated[StaffAccount, Depends(get_current_account)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RequeueRegistrationResponse:
    service = ManualReviewService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.requeue_registration(actor=account, reg_id=reg_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
