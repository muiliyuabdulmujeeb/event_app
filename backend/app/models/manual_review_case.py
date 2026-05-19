from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.payment import Payment
    from app.models.registration import Registration
    from app.models.staff import StaffAccount


class ManualReviewCaseType(str, enum.Enum):
    LATE_PAYMENT_SUCCESS = "late_payment_success"
    PAYMENT_TIMEOUT_REQUEUE = "payment_timeout_requeue"
    PAYMENT_FAILURE_REQUEUE = "payment_failure_requeue"
    EXCEPTION_REGISTRATION_ISSUE = "exception_registration_issue"
    OVERFLOW_POLICY_CANCELLATION = "overflow_policy_cancellation"
    OTHER = "other"


class ManualReviewCaseStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ManualReviewCase(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "manual_review_cases"
    __table_args__ = (
        Index("ix_manual_review_cases_status", "status"),
        Index("ix_manual_review_cases_event_id", "event_id"),
        Index("ix_manual_review_cases_registration_id", "registration_id"),
        Index("ix_manual_review_cases_payment_id", "payment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("mrc"))
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    registration_id: Mapped[str | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    case_type: Mapped[ManualReviewCaseType] = mapped_column(
        Enum(ManualReviewCaseType, name="manual_review_case_type", native_enum=False, length=40),
        nullable=False,
    )
    status: Mapped[ManualReviewCaseStatus] = mapped_column(
        Enum(ManualReviewCaseStatus, name="manual_review_case_status", native_enum=False, length=24),
        nullable=False,
        default=ManualReviewCaseStatus.OPEN,
        server_default=ManualReviewCaseStatus.OPEN.value,
    )
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event | None"] = relationship(back_populates="manual_review_cases")
    registration: Mapped["Registration | None"] = relationship(back_populates="manual_review_cases")
    payment: Mapped["Payment | None"] = relationship(back_populates="manual_review_cases")
    created_by_staff: Mapped["StaffAccount | None"] = relationship(
        back_populates="created_manual_review_cases",
        foreign_keys=[created_by_staff_id],
    )
    assigned_to_staff: Mapped["StaffAccount | None"] = relationship(
        back_populates="assigned_manual_review_cases",
        foreign_keys=[assigned_to_staff_id],
    )
    resolved_by_staff: Mapped["StaffAccount | None"] = relationship(
        back_populates="resolved_manual_review_cases",
        foreign_keys=[resolved_by_staff_id],
    )


from app.models.event import Event  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.staff import StaffAccount  # noqa: E402
