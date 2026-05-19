from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.registration import Registration


class RefundRequestStatus(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class RefundRequestedBy(str, enum.Enum):
    PUBLIC = "public"
    ADMIN = "admin"
    SYSTEM = "system"


class RefundRequest(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "refund_requests"
    __table_args__ = (
        Index("ix_refund_requests_registration_id", "registration_id"),
        Index("ix_refund_requests_status", "status"),
        Index("ix_refund_requests_requested_at", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("rrq"))
    registration_id: Mapped[str] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[RefundRequestStatus] = mapped_column(
        Enum(RefundRequestStatus, name="refund_request_status", native_enum=False, length=16),
        nullable=False,
        default=RefundRequestStatus.REQUESTED,
        server_default=RefundRequestStatus.REQUESTED.value,
    )
    requested_by: Mapped[RefundRequestedBy] = mapped_column(
        Enum(RefundRequestedBy, name="refund_requested_by", native_enum=False, length=16),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration: Mapped["Registration"] = relationship(back_populates="refund_requests")


from app.models.registration import Registration  # noqa: E402
