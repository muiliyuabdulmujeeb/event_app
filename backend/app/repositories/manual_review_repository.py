from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.manual_review_case import ManualReviewCase, ManualReviewCaseStatus, ManualReviewCaseType
from app.models.payment import Payment
from app.models.registration import BatchRegistration, Registration


@dataclass(frozen=True)
class ManualReviewCaseFilters:
    status: ManualReviewCaseStatus | None = None
    case_type: ManualReviewCaseType | None = None
    event_id: str | None = None
    registration_id: str | None = None
    payment_id: str | None = None


OPEN_MANUAL_REVIEW_STATUSES = (
    ManualReviewCaseStatus.OPEN,
    ManualReviewCaseStatus.IN_PROGRESS,
)


class ManualReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_case(self, case: ManualReviewCase) -> ManualReviewCase:
        self.session.add(case)
        await self.session.flush()
        return case

    async def get_case_by_id(
        self,
        case_id: str,
        *,
        for_update: bool = False,
    ) -> ManualReviewCase | None:
        query = self._base_query().where(ManualReviewCase.id == case_id)
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_cases(self, filters: ManualReviewCaseFilters) -> list[ManualReviewCase]:
        query = self._base_query().order_by(ManualReviewCase.created_at.desc(), ManualReviewCase.id.desc())
        if filters.status is not None:
            query = query.where(ManualReviewCase.status == filters.status)
        if filters.case_type is not None:
            query = query.where(ManualReviewCase.case_type == filters.case_type)
        if filters.event_id is not None:
            query = query.where(ManualReviewCase.event_id == filters.event_id)
        if filters.registration_id is not None:
            query = query.where(ManualReviewCase.registration_id == filters.registration_id)
        if filters.payment_id is not None:
            query = query.where(ManualReviewCase.payment_id == filters.payment_id)

        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_open_case_for_registration(self, registration_id: str) -> ManualReviewCase | None:
        result = await self.session.execute(
            self._base_query()
            .where(
                ManualReviewCase.registration_id == registration_id,
                ManualReviewCase.status.in_(OPEN_MANUAL_REVIEW_STATUSES),
            )
            .order_by(ManualReviewCase.created_at.desc(), ManualReviewCase.id.desc())
        )
        return result.scalars().first()

    async def get_open_case_for_payment(self, payment_id: str) -> ManualReviewCase | None:
        result = await self.session.execute(
            self._base_query()
            .where(
                ManualReviewCase.payment_id == payment_id,
                ManualReviewCase.status.in_(OPEN_MANUAL_REVIEW_STATUSES),
            )
            .order_by(ManualReviewCase.created_at.desc(), ManualReviewCase.id.desc())
        )
        return result.scalars().first()

    def _base_query(self) -> Select[tuple[ManualReviewCase]]:
        return select(ManualReviewCase).options(
            selectinload(ManualReviewCase.registration).selectinload(Registration.event),
            selectinload(ManualReviewCase.registration).selectinload(Registration.payment),
            selectinload(ManualReviewCase.registration).selectinload(Registration.payments),
            selectinload(ManualReviewCase.payment).selectinload(Payment.registration),
            selectinload(ManualReviewCase.payment).selectinload(Payment.batch_registration),
            selectinload(ManualReviewCase.payment)
            .selectinload(Payment.batch_registration)
            .selectinload(BatchRegistration.registrations),
        )
