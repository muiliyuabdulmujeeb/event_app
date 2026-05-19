from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.manual_review_case import ManualReviewCase
    from app.models.notification import StaffNotification
    from app.models.staff_event_authorization import StaffEventAuthorization


class StaffRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"


class StaffAccessMode(str, enum.Enum):
    ALL_EVENTS = "all_events"
    SELECTED_EVENTS = "selected_events"


class StaffAccount(Base, CreatedAtMixin):
    __tablename__ = "staff_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("stf"))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, name="staff_role", native_enum=False, length=16),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_events: Mapped[list["Event"]] = relationship(back_populates="created_by_account")
    access_mode_record: Mapped["StaffAccessModeRecord | None"] = relationship(
        back_populates="staff",
        cascade="all, delete-orphan",
        uselist=False,
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="staff",
        cascade="all, delete-orphan",
    )
    event_access_entries: Mapped[list["StaffEventAccess"]] = relationship(
        back_populates="staff",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["StaffNotification"]] = relationship(
        back_populates="staff",
        cascade="all, delete-orphan",
    )
    event_authorizations: Mapped[list["StaffEventAuthorization"]] = relationship(
        back_populates="staff",
        cascade="all, delete-orphan",
        foreign_keys="StaffEventAuthorization.staff_id",
    )
    granted_event_authorizations: Mapped[list["StaffEventAuthorization"]] = relationship(
        back_populates="granted_by_account",
        foreign_keys="StaffEventAuthorization.granted_by_staff_id",
    )
    revoked_event_authorizations: Mapped[list["StaffEventAuthorization"]] = relationship(
        back_populates="revoked_by_account",
        foreign_keys="StaffEventAuthorization.revoked_by_staff_id",
    )
    created_manual_review_cases: Mapped[list["ManualReviewCase"]] = relationship(
        back_populates="created_by_staff",
        foreign_keys="ManualReviewCase.created_by_staff_id",
    )
    assigned_manual_review_cases: Mapped[list["ManualReviewCase"]] = relationship(
        back_populates="assigned_to_staff",
        foreign_keys="ManualReviewCase.assigned_to_staff_id",
    )
    resolved_manual_review_cases: Mapped[list["ManualReviewCase"]] = relationship(
        back_populates="resolved_by_staff",
        foreign_keys="ManualReviewCase.resolved_by_staff_id",
    )


class StaffAccessModeRecord(Base):
    __tablename__ = "staff_access_mode"

    staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[StaffAccessMode] = mapped_column(
        Enum(StaffAccessMode, name="staff_access_mode", native_enum=False, length=24),
        nullable=False,
        default=StaffAccessMode.ALL_EVENTS,
        server_default=StaffAccessMode.ALL_EVENTS.value,
    )

    staff: Mapped["StaffAccount"] = relationship(back_populates="access_mode_record")


class StaffEventAccess(Base):
    __tablename__ = "staff_event_access"

    staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )

    staff: Mapped["StaffAccount"] = relationship(back_populates="event_access_entries")
    event: Mapped["Event"] = relationship(back_populates="staff_access_entries")


class RefreshToken(Base, CreatedAtMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    staff: Mapped["StaffAccount"] = relationship(back_populates="refresh_tokens")


from app.models.event import Event  # noqa: E402
from app.models.manual_review_case import ManualReviewCase  # noqa: E402
from app.models.notification import StaffNotification  # noqa: E402
from app.models.staff_event_authorization import StaffEventAuthorization  # noqa: E402
