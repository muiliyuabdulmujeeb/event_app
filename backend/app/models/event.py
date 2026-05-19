from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.registration import BatchRegistration, Registration
    from app.models.exception_registration_offer import ExceptionRegistrationOffer
    from app.models.manual_review_case import ManualReviewCase
    from app.models.staff import StaffAccount, StaffEventAccess
    from app.models.staff_event_authorization import StaffEventAuthorization


class EventState(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OverflowRule(str, enum.Enum):
    HARD_REJECTION = "hard_rejection"
    WAITLIST = "waitlist"


class FieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    PHONE = "phone"
    EMAIL = "email"


class Event(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity_positive"),
        CheckConstraint("prefix ~ '^[A-Z0-9]{2,5}$'", name="prefix_format"),
        Index("ix_events_event_date", "event_date"),
        Index("ix_events_state", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("evt"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_free: Mapped[bool] = mapped_column(
        Boolean,
        Computed("price = 0", persisted=True),
        nullable=False,
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overflow_rule: Mapped[OverflowRule] = mapped_column(
        Enum(OverflowRule, name="overflow_rule", native_enum=False, length=32),
        nullable=False,
        default=OverflowRule.HARD_REJECTION,
    )
    state: Mapped[EventState] = mapped_column(
        Enum(EventState, name="event_state", native_enum=False, length=32),
        nullable=False,
        default=EventState.DRAFT,
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_by_account: Mapped["StaffAccount"] = relationship(back_populates="created_events")
    field_definitions: Mapped[list["EventFieldDefinition"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventFieldDefinition.display_order",
    )
    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    batch_registrations: Mapped[list["BatchRegistration"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    staff_access_entries: Mapped[list["StaffEventAccess"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    staff_authorizations: Mapped[list["StaffEventAuthorization"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    exception_offers: Mapped[list["ExceptionRegistrationOffer"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    manual_review_cases: Mapped[list["ManualReviewCase"]] = relationship(back_populates="event")


class EventFieldDefinition(Base):
    __tablename__ = "event_field_definitions"
    __table_args__ = (
        UniqueConstraint("event_id", "display_order", name="uq_event_field_definitions_order"),
        CheckConstraint("display_order > 0", name="display_order_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("fld"))
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(
        Enum(FieldType, name="field_type", native_enum=False, length=16),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    event: Mapped["Event"] = relationship(back_populates="field_definitions")
    registration_values: Mapped[list["RegistrationFieldValue"]] = relationship(
        back_populates="field_definition",
        cascade="all, delete-orphan",
    )


from app.models.registration import RegistrationFieldValue  # noqa: E402
from app.models.exception_registration_offer import ExceptionRegistrationOffer  # noqa: E402
from app.models.manual_review_case import ManualReviewCase  # noqa: E402
from app.models.staff_event_authorization import StaffEventAuthorization  # noqa: E402
