from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, as_http_exception
from app.core.dependencies import get_app_settings, get_db_session, require_admin
from app.models.exception_registration_offer import ExceptionRegistrationOfferStatus
from app.models.staff import StaffAccount
from app.schemas.event import (
    AdminEventDetailResponse,
    AdminEventListResponse,
    EventCreateRequest,
    EventOverflowRuleUpdateRequest,
    EventOverflowRuleUpdateResponse,
    EventStateUpdateRequest,
    EventUpdateRequest,
)
from app.schemas.exception_registration import (
    ExceptionRegistrationOfferAuditListResponse,
    ExceptionRegistrationOfferCreateRequest,
    ExceptionRegistrationOfferListResponse,
    ExceptionRegistrationOfferResponse,
    ExceptionRegistrationOfferRevokeRequest,
    ExceptionRegistrationOfferRevokeResponse,
)
from app.schemas.staff import (
    EventAuthorizationListResponse,
    EventAuthorizationResponse,
    EventAuthorizationRevokeResponse,
    EventAuthorizationUpdateRequest,
)
from app.services.event_authorization_service import EventAuthorizationService
from app.services.exception_registration_service import ExceptionRegistrationService
from app.services.event_service import (
    EventService,
)
from app.services.email_service import EmailService

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


async def _commit_or_rollback(session: AsyncSession) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=AdminEventListResponse)
async def list_admin_events(
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventListResponse:
    service = EventService(session=session)
    return await service.list_admin_events()


@router.get("/{event_id}", response_model=AdminEventDetailResponse)
async def get_admin_event_detail(
    event_id: str,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminEventDetailResponse:
    service = EventService(session=session)
    try:
        return await service.get_admin_event_detail(event_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.post("", response_model=AdminEventDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreateRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminEventDetailResponse:
    service = EventService(session=session, settings=settings)
    try:
        response = await service.create_event(payload=payload, created_by=account)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.get("/{event_id}/authorizations", response_model=EventAuthorizationListResponse)
async def list_event_authorizations(
    event_id: str,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventAuthorizationListResponse:
    service = EventAuthorizationService(session=session)
    try:
        return await service.list_event_authorizations(actor=account, event_id=event_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.put("/{event_id}/authorizations/{account_id}", response_model=EventAuthorizationResponse)
async def upsert_event_authorization(
    event_id: str,
    account_id: str,
    payload: EventAuthorizationUpdateRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventAuthorizationResponse:
    service = EventAuthorizationService(session=session)
    try:
        response = await service.upsert_event_authorization(
            actor=account,
            event_id=event_id,
            account_id=account_id,
            payload=payload,
        )
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.delete("/{event_id}/authorizations/{account_id}", response_model=EventAuthorizationRevokeResponse)
async def revoke_event_authorization(
    event_id: str,
    account_id: str,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventAuthorizationRevokeResponse:
    service = EventAuthorizationService(session=session)
    try:
        response = await service.revoke_event_authorization(
            actor=account,
            event_id=event_id,
            account_id=account_id,
        )
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.post(
    "/{event_id}/exception-offers",
    response_model=ExceptionRegistrationOfferResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exception_offer(
    event_id: str,
    payload: ExceptionRegistrationOfferCreateRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ExceptionRegistrationOfferResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    try:
        response = await service.create_offer(actor=account, event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.get("/{event_id}/exception-offers", response_model=ExceptionRegistrationOfferListResponse)
async def list_exception_offers(
    event_id: str,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    offer_status: Annotated[ExceptionRegistrationOfferStatus | None, Query(alias="status")] = None,
    target_email: str | None = None,
) -> ExceptionRegistrationOfferListResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    try:
        return await service.list_offers(
            actor=account,
            event_id=event_id,
            status=offer_status,
            target_email=target_email,
        )
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.get(
    "/{event_id}/exception-offers/{offer_id}/audit",
    response_model=ExceptionRegistrationOfferAuditListResponse,
)
async def get_exception_offer_audit(
    event_id: str,
    offer_id: str,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ExceptionRegistrationOfferAuditListResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    try:
        return await service.get_offer_audit(actor=account, event_id=event_id, offer_id=offer_id)
    except AppError as exc:
        raise as_http_exception(exc) from exc


@router.patch(
    "/{event_id}/exception-offers/{offer_id}/revoke",
    response_model=ExceptionRegistrationOfferRevokeResponse,
)
async def revoke_exception_offer(
    event_id: str,
    offer_id: str,
    payload: ExceptionRegistrationOfferRevokeRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ExceptionRegistrationOfferRevokeResponse:
    service = ExceptionRegistrationService(session=session, settings=settings)
    try:
        response = await service.revoke_offer(
            actor=account,
            event_id=event_id,
            offer_id=offer_id,
            reason=payload.reason,
        )
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        if exc.commit_changes:
            await _commit_or_rollback(session)
        else:
            await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/{event_id}/overflow-rule", response_model=EventOverflowRuleUpdateResponse)
async def update_event_overflow_rule(
    event_id: str,
    payload: EventOverflowRuleUpdateRequest,
    account: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> EventOverflowRuleUpdateResponse:
    service = EventService(session=session, settings=settings)
    try:
        response = await service.update_overflow_rule(actor=account, event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        return response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/{event_id}", response_model=AdminEventDetailResponse)
async def update_event(
    event_id: str,
    payload: EventUpdateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminEventDetailResponse:
    service = EventService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.update_event(event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc


@router.patch("/{event_id}/state", response_model=AdminEventDetailResponse)
async def update_event_state(
    event_id: str,
    payload: EventStateUpdateRequest,
    _: Annotated[StaffAccount, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminEventDetailResponse:
    service = EventService(session=session, settings=settings)
    email_service = EmailService(settings=settings)
    try:
        result = await service.update_event_state(event_id=event_id, payload=payload)
        await _commit_or_rollback(session)
        email_service.enqueue_messages(result.email_messages)
        return result.response
    except AppError as exc:
        await session.rollback()
        raise as_http_exception(exc) from exc
