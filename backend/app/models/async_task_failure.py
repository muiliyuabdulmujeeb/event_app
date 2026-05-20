from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.payment import Payment
    from app.models.registration import Registration
    from app.models.staff import StaffAccount


class AsyncTaskType(str, enum.Enum):
    EMAIL = "email"
    PAYMENT = "payment"
    NOTIFICATION = "notification"
    EXPORT = "export"
    OTHER = "other"


class AsyncTaskFailureStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AsyncTaskFailure(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "async_task_failures"
    __table_args__ = (
        CheckConstraint("attempt_count > 0", name="attempt_count_positive"),
        Index("ix_async_task_failures_status", "status"),
        Index("ix_async_task_failures_task_type", "task_type"),
        Index("ix_async_task_failures_event_id", "event_id"),
        Index("ix_async_task_failures_registration_id", "registration_id"),
        Index("ix_async_task_failures_payment_id", "payment_id"),
        Index("ix_async_task_failures_final_failed_at", "final_failed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("atf"))
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[AsyncTaskType] = mapped_column(
        Enum(AsyncTaskType, name="async_task_type", native_enum=False, length=24),
        nullable=False,
    )
    failure_category: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AsyncTaskFailureStatus] = mapped_column(
        Enum(AsyncTaskFailureStatus, name="async_task_failure_status", native_enum=False, length=24),
        nullable=False,
        default=AsyncTaskFailureStatus.OPEN,
        server_default=AsyncTaskFailureStatus.OPEN.value,
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    registration_id: Mapped[str | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_attempts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_class: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    final_failed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    event: Mapped["Event | None"] = relationship(back_populates="async_task_failures")
    registration: Mapped["Registration | None"] = relationship(back_populates="async_task_failures")
    payment: Mapped["Payment | None"] = relationship(back_populates="async_task_failures")
    acknowledged_by_account: Mapped["StaffAccount | None"] = relationship(
        back_populates="acknowledged_async_task_failures",
        foreign_keys=[acknowledged_by_staff_id],
    )
    resolved_by_account: Mapped["StaffAccount | None"] = relationship(
        back_populates="resolved_async_task_failures",
        foreign_keys=[resolved_by_staff_id],
    )


from app.models.event import Event  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.staff import StaffAccount  # noqa: E402
