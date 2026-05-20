from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AsyncTaskFailureForbiddenError,
    AsyncTaskFailureNotFoundError,
    AsyncTaskFailureValidationError,
    StaffAccountNotFoundError,
)
from app.core.security import utc_now
from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskFailureStatus, AsyncTaskType
from app.models.staff import StaffAccessMode, StaffAccount, StaffRole
from app.repositories.async_task_failure_repository import AsyncTaskFailureFilters, AsyncTaskFailureRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.staff_repository import StaffRepository
from app.schemas.async_task_failure import (
    AsyncTaskFailureListResponse,
    AsyncTaskFailureResponse,
    AsyncTaskFailureUpdateRequest,
)
from app.services.event_authorization_service import EventAuthorizationService


@dataclass
class AsyncTaskFailureService:
    session: AsyncSession

    def __post_init__(self) -> None:
        self.repository = AsyncTaskFailureRepository(self.session)
        self.payment_repository = PaymentRepository(self.session)
        self.registration_repository = RegistrationRepository(self.session)
        self.staff_repository = StaffRepository(self.session)
        self.authorization_service = EventAuthorizationService(self.session)

    async def create_failure(
        self,
        *,
        task_name: str,
        task_type: AsyncTaskType,
        failure_category: str,
        error_class: str,
        error_message: str,
        provider_attempts: list[dict[str, Any]] | None,
        attempt_count: int,
        payload_metadata: dict[str, Any] | None,
        final_failed_at: datetime,
        event_id: str | None = None,
        registration_id: str | None = None,
        reg_id: str | None = None,
        payment_id: str | None = None,
        payment_reference: str | None = None,
    ) -> AsyncTaskFailure:
        resolved_registration_id = registration_id
        resolved_payment_id = payment_id
        resolved_event_id = event_id

        if resolved_registration_id is None and reg_id:
            registration = await self.registration_repository.get_registration_by_reg_id(reg_id)
            if registration is not None:
                resolved_registration_id = registration.id
                if resolved_event_id is None:
                    resolved_event_id = registration.event_id

        if resolved_payment_id is None and payment_reference:
            payment = await self.payment_repository.get_by_reference(payment_reference)
            if payment is not None:
                resolved_payment_id = payment.id
                if resolved_event_id is None:
                    if payment.registration is not None:
                        resolved_event_id = payment.registration.event_id
                    elif payment.batch_registration is not None:
                        resolved_event_id = payment.batch_registration.event_id

        failure = AsyncTaskFailure(
            task_name=task_name,
            task_type=task_type,
            failure_category=failure_category,
            status=AsyncTaskFailureStatus.OPEN,
            event_id=resolved_event_id,
            registration_id=resolved_registration_id,
            payment_id=resolved_payment_id,
            provider_attempts=provider_attempts,
            attempt_count=attempt_count,
            error_class=error_class,
            error_message=error_message,
            payload_metadata=payload_metadata,
            final_failed_at=final_failed_at,
        )
        return await self.repository.create_failure(failure)

    async def list_failures(
        self,
        *,
        actor: StaffAccount,
        filters: AsyncTaskFailureFilters,
    ) -> AsyncTaskFailureListResponse:
        account = await self._load_actor(actor.id)
        if filters.event_id is not None and not await self._can_access_event_failures(account, filters.event_id):
            raise AsyncTaskFailureForbiddenError("You do not have permission to access dead-letter entries for this event.")

        failures = await self.repository.list_failures(filters)
        accessible_failures = await self._filter_accessible_failures(account, failures)
        return AsyncTaskFailureListResponse(
            failures=[self._build_response(failure) for failure in accessible_failures],
            total=len(accessible_failures),
        )

    async def get_failure(
        self,
        *,
        actor: StaffAccount,
        failure_id: str,
    ) -> AsyncTaskFailureResponse:
        account = await self._load_actor(actor.id)
        failure = await self.repository.get_failure_by_id(failure_id)
        if failure is None:
            raise AsyncTaskFailureNotFoundError("Dead-letter entry not found.")
        if not await self._can_access_failure(account, failure):
            raise AsyncTaskFailureForbiddenError("You do not have permission to access this dead-letter entry.")
        return self._build_response(failure)

    async def update_failure(
        self,
        *,
        actor: StaffAccount,
        failure_id: str,
        payload: AsyncTaskFailureUpdateRequest,
    ) -> AsyncTaskFailureResponse:
        account = await self._load_actor(actor.id)
        failure = await self.repository.get_failure_by_id(failure_id)
        if failure is None:
            raise AsyncTaskFailureNotFoundError("Dead-letter entry not found.")
        if not await self._can_access_failure(account, failure):
            raise AsyncTaskFailureForbiddenError("You do not have permission to update this dead-letter entry.")

        self._validate_status_transition(current_status=failure.status, next_status=payload.status)
        now = utc_now()
        if payload.status == AsyncTaskFailureStatus.ACKNOWLEDGED:
            failure.status = AsyncTaskFailureStatus.ACKNOWLEDGED
            failure.acknowledged_by_staff_id = account.id
            failure.acknowledged_at = now
            if payload.resolution_notes is not None:
                failure.resolution_notes = payload.resolution_notes
        elif payload.status == AsyncTaskFailureStatus.RESOLVED:
            failure.status = AsyncTaskFailureStatus.RESOLVED
            failure.resolved_by_staff_id = account.id
            failure.resolved_at = now
            if payload.resolution_notes is not None:
                failure.resolution_notes = payload.resolution_notes

        await self.repository.save_failure(failure)
        refreshed_failure = await self.repository.get_failure_by_id(failure.id)
        if refreshed_failure is None:
            raise AsyncTaskFailureNotFoundError("Dead-letter entry not found.")
        return self._build_response(refreshed_failure)

    async def _load_actor(self, actor_id: str) -> StaffAccount:
        account = await self.staff_repository.get_by_id_with_access(actor_id)
        if account is None:
            raise StaffAccountNotFoundError("Staff account not found.")
        return account

    async def _filter_accessible_failures(
        self,
        account: StaffAccount,
        failures: list[AsyncTaskFailure],
    ) -> list[AsyncTaskFailure]:
        if account.role == StaffRole.ADMIN:
            return failures

        access_cache: dict[str, bool] = {}
        accessible: list[AsyncTaskFailure] = []
        for failure in failures:
            if failure.event_id is None:
                continue
            allowed = access_cache.get(failure.event_id)
            if allowed is None:
                allowed = await self._can_access_event_failures(account, failure.event_id)
                access_cache[failure.event_id] = allowed
            if allowed:
                accessible.append(failure)
        return accessible

    async def _can_access_failure(self, account: StaffAccount, failure: AsyncTaskFailure) -> bool:
        if account.role == StaffRole.ADMIN:
            return True
        if failure.event_id is None:
            return False
        return await self._can_access_event_failures(account, failure.event_id)

    async def _can_access_event_failures(self, account: StaffAccount, event_id: str) -> bool:
        if account.role == StaffRole.ADMIN:
            return True
        if not self._can_access_event(account, event_id):
            return False
        return await self.authorization_service.has_delegated_permission(
            actor_id=account.id,
            event_id=event_id,
            permission_name="can_manage_manual_reviews",
        )

    def _can_access_event(self, account: StaffAccount, event_id: str) -> bool:
        mode = account.access_mode_record.mode if account.access_mode_record is not None else StaffAccessMode.ALL_EVENTS
        if mode == StaffAccessMode.ALL_EVENTS:
            return True
        return any(entry.event_id == event_id for entry in account.event_access_entries)

    def _build_response(self, failure: AsyncTaskFailure) -> AsyncTaskFailureResponse:
        return AsyncTaskFailureResponse(
            id=failure.id,
            task_name=failure.task_name,
            task_type=failure.task_type,
            failure_category=failure.failure_category,
            status=failure.status,
            event_id=failure.event_id,
            registration_id=failure.registration_id,
            reg_id=failure.registration.reg_id if failure.registration is not None else None,
            payment_id=failure.payment_id,
            payment_reference=failure.payment.payment_reference if failure.payment is not None else None,
            acknowledged_by_staff_id=failure.acknowledged_by_staff_id,
            acknowledged_at=failure.acknowledged_at,
            resolved_by_staff_id=failure.resolved_by_staff_id,
            resolved_at=failure.resolved_at,
            resolution_notes=failure.resolution_notes,
            provider_attempts=failure.provider_attempts,
            attempt_count=failure.attempt_count,
            error_class=failure.error_class,
            error_message=failure.error_message,
            payload_metadata=failure.payload_metadata,
            final_failed_at=failure.final_failed_at,
            created_at=failure.created_at,
            updated_at=failure.updated_at,
        )

    def _validate_status_transition(
        self,
        *,
        current_status: AsyncTaskFailureStatus,
        next_status: AsyncTaskFailureStatus,
    ) -> None:
        allowed_transitions = {
            AsyncTaskFailureStatus.OPEN: {
                AsyncTaskFailureStatus.ACKNOWLEDGED,
                AsyncTaskFailureStatus.RESOLVED,
            },
            AsyncTaskFailureStatus.ACKNOWLEDGED: {AsyncTaskFailureStatus.RESOLVED},
            AsyncTaskFailureStatus.RESOLVED: set(),
        }
        if next_status not in allowed_transitions[current_status]:
            raise AsyncTaskFailureValidationError(
                f"Cannot change dead-letter status from '{current_status.value}' to '{next_status.value}'."
            )
