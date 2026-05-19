from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event
from app.models.payment import Payment, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestStatus
from app.models.registration import Registration


ACTIVE_REFUND_REQUEST_STATUSES = (
    RefundRequestStatus.REQUESTED,
    RefundRequestStatus.APPROVED,
)


class RefundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def registration_has_successful_payment_history(self, registration_id: str) -> bool:
        result = await self.session.execute(
            select(Payment.id).where(
                Payment.registration_id == registration_id,
                Payment.status == PaymentStatus.SUCCESSFUL,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_active_refund_request_for_registration(self, registration_id: str) -> RefundRequest | None:
        result = await self.session.execute(
            select(RefundRequest)
            .where(
                RefundRequest.registration_id == registration_id,
                RefundRequest.status.in_(ACTIVE_REFUND_REQUEST_STATUSES),
            )
            .order_by(RefundRequest.requested_at.desc(), RefundRequest.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_refund_request_for_registration(self, registration_id: str) -> RefundRequest | None:
        result = await self.session.execute(
            select(RefundRequest)
            .where(RefundRequest.registration_id == registration_id)
            .order_by(RefundRequest.requested_at.desc(), RefundRequest.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_refund_request(self, refund_request: RefundRequest) -> RefundRequest:
        self.session.add(refund_request)
        await self.session.flush()
        return refund_request

    async def get_refund_request_by_id(
        self,
        refund_request_id: str,
        *,
        for_update: bool = False,
    ) -> RefundRequest | None:
        query: Select[tuple[RefundRequest]] = (
            select(RefundRequest)
            .where(RefundRequest.id == refund_request_id)
            .options(
                selectinload(RefundRequest.registration).selectinload(Registration.event).selectinload(Event.field_definitions),
                selectinload(RefundRequest.registration).selectinload(Registration.payment),
                selectinload(RefundRequest.registration).selectinload(Registration.payments),
                selectinload(RefundRequest.registration).selectinload(Registration.refund_requests),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_refund_requests(
        self,
        *,
        status: RefundRequestStatus | None = None,
        event_id: str | None = None,
        reg_id: str | None = None,
    ) -> Sequence[RefundRequest]:
        query: Select[tuple[RefundRequest]] = (
            select(RefundRequest)
            .join(Registration, Registration.id == RefundRequest.registration_id)
            .options(selectinload(RefundRequest.registration))
            .order_by(desc(RefundRequest.requested_at), desc(RefundRequest.id))
        )
        if status is not None:
            query = query.where(RefundRequest.status == status)
        if event_id is not None:
            query = query.where(Registration.event_id == event_id)
        if reg_id is not None:
            query = query.where(Registration.reg_id == reg_id)
        result = await self.session.execute(query)
        return result.scalars().all()
