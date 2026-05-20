from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskFailureStatus, AsyncTaskType
from app.models.payment import Payment
from app.models.registration import Registration


@dataclass(frozen=True)
class AsyncTaskFailureFilters:
    task_type: AsyncTaskType | None = None
    status: AsyncTaskFailureStatus | None = None
    event_id: str | None = None
    registration_id: str | None = None
    payment_id: str | None = None


class AsyncTaskFailureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_failure(self, failure: AsyncTaskFailure) -> AsyncTaskFailure:
        self.session.add(failure)
        await self.session.flush()
        return failure

    async def save_failure(self, failure: AsyncTaskFailure) -> AsyncTaskFailure:
        self.session.add(failure)
        await self.session.flush()
        return failure

    async def get_failure_by_id(self, failure_id: str) -> AsyncTaskFailure | None:
        result = await self.session.execute(self._base_query().where(AsyncTaskFailure.id == failure_id))
        return result.scalar_one_or_none()

    async def list_failures(self, filters: AsyncTaskFailureFilters) -> list[AsyncTaskFailure]:
        query = self._base_query().order_by(AsyncTaskFailure.final_failed_at.desc(), AsyncTaskFailure.id.desc())
        if filters.task_type is not None:
            query = query.where(AsyncTaskFailure.task_type == filters.task_type)
        if filters.status is not None:
            query = query.where(AsyncTaskFailure.status == filters.status)
        if filters.event_id is not None:
            query = query.where(AsyncTaskFailure.event_id == filters.event_id)
        if filters.registration_id is not None:
            query = query.where(AsyncTaskFailure.registration_id == filters.registration_id)
        if filters.payment_id is not None:
            query = query.where(AsyncTaskFailure.payment_id == filters.payment_id)

        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    def _base_query(self) -> Select[tuple[AsyncTaskFailure]]:
        return select(AsyncTaskFailure).options(
            selectinload(AsyncTaskFailure.registration).selectinload(Registration.event),
            selectinload(AsyncTaskFailure.registration).selectinload(Registration.payment),
            selectinload(AsyncTaskFailure.payment).selectinload(Payment.registration),
            selectinload(AsyncTaskFailure.payment).selectinload(Payment.batch_registration),
        )
