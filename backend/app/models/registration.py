from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.event import Event, EventFieldDefinition
    from app.models.notification import UserNotification
    from app.models.payment import Payment
    from app.models.waitlist_promotion_offer import WaitlistPromotionOffer


class RegistrationState(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"
    WAITLISTED = "waitlisted"


class BatchRegistration(Base, CreatedAtMixin):
    __tablename__ = "batch_registrations"
    __table_args__ = (CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("bat"))
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    submitter_email: Mapped[str] = mapped_column(String(320), nullable=False)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="batch_registrations")
    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="batch_registration",
        cascade="all, delete-orphan",
    )
    payment: Mapped["Payment | None"] = relationship(
        back_populates="batch_registration",
        uselist=False,
    )


class Registration(Base, UpdatedAtMixin):
    __tablename__ = "registrations"
    __table_args__ = (
        CheckConstraint("waitlist_position IS NULL OR waitlist_position > 0", name="waitlist_position_positive"),
        CheckConstraint(
            "reg_id ~ '^[A-Z0-9]{2,5}-[0-9]{4}-[A-Z0-9]{6}$'",
            name="reg_id_format",
        ),
        Index("ix_registrations_state", "state"),
        Index("ix_registrations_registered_at", "registered_at"),
        Index("ix_registrations_email", "email"),
        Index("ix_registrations_waitlist_queue", "event_id", "state", "waitlist_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("rdb"))
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    reg_id: Mapped[str] = mapped_column(String(18), nullable=False, unique=True, index=True)
    state: Mapped[RegistrationState] = mapped_column(
        Enum(RegistrationState, name="registration_state", native_enum=False, length=24),
        nullable=False,
    )
    is_checked_in: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waitlist_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("batch_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped["Event"] = relationship(back_populates="registrations")
    batch_registration: Mapped["BatchRegistration | None"] = relationship(back_populates="registrations")
    field_values: Mapped[list["RegistrationFieldValue"]] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
    )
    payment: Mapped["Payment | None"] = relationship(
        back_populates="registration",
        uselist=False,
    )
    user_notifications: Mapped[list["UserNotification"]] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
    )
    waitlist_promotion_offer: Mapped["WaitlistPromotionOffer | None"] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
        uselist=False,
    )


class RegistrationFieldValue(Base):
    __tablename__ = "registration_field_values"
    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "field_definition_id",
            name="uq_registration_field_values_registration_field",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("rfv"))
    registration_id: Mapped[str] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_definition_id: Mapped[str] = mapped_column(
        ForeignKey("event_field_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)

    registration: Mapped["Registration"] = relationship(back_populates="field_values")
    field_definition: Mapped["EventFieldDefinition"] = relationship(back_populates="registration_values")


from app.models.event import Event, EventFieldDefinition  # noqa: E402
from app.models.notification import UserNotification  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer  # noqa: E402
