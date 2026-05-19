from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.staff import StaffAccount


class StaffEventAuthorization(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "staff_event_authorizations"

    staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_manage_exception_offers: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    can_change_overflow_rule: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    can_manage_manual_reviews: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    can_requeue_registrations: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    granted_by_staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revoked_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    staff: Mapped["StaffAccount"] = relationship(
        back_populates="event_authorizations",
        foreign_keys=[staff_id],
    )
    event: Mapped["Event"] = relationship(back_populates="staff_authorizations")
    granted_by_account: Mapped["StaffAccount"] = relationship(
        back_populates="granted_event_authorizations",
        foreign_keys=[granted_by_staff_id],
    )
    revoked_by_account: Mapped["StaffAccount | None"] = relationship(
        back_populates="revoked_event_authorizations",
        foreign_keys=[revoked_by_staff_id],
    )
