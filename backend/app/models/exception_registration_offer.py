from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.exception_registration_offer_audit import ExceptionRegistrationOfferAudit
    from app.models.registration import Registration
    from app.models.staff import StaffAccount


class ExceptionRegistrationOfferStatus(str, enum.Enum):
    ISSUED = "issued"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ExceptionRegistrationOffer(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "exception_registration_offers"
    __table_args__ = (
        UniqueConstraint("used_registration_id", name="uq_exception_registration_offers_used_registration_id"),
        Index("ix_exception_registration_offers_event_status", "event_id", "status"),
        Index("ix_exception_registration_offers_target_email", "target_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("exo"))
    public_token: Mapped[str] = mapped_column(
        String(26),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: str(ulid.new()),
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issued_by_staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_email: Mapped[str] = mapped_column(String(320), nullable=False)
    target_first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_reg_id: Mapped[str | None] = mapped_column(String(18), nullable=True)
    payment_waived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    capacity_override: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ExceptionRegistrationOfferStatus] = mapped_column(
        Enum(
            ExceptionRegistrationOfferStatus,
            name="exception_registration_offer_status",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=ExceptionRegistrationOfferStatus.ISSUED,
        server_default=ExceptionRegistrationOfferStatus.ISSUED.value,
    )
    used_registration_id: Mapped[str | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    gateway_checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="exception_offers")
    used_registration: Mapped["Registration | None"] = relationship(back_populates="exception_offer")
    issued_by_account: Mapped["StaffAccount"] = relationship(foreign_keys=[issued_by_staff_id])
    audit_entries: Mapped[list["ExceptionRegistrationOfferAudit"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan",
        order_by="ExceptionRegistrationOfferAudit.created_at.asc()",
    )


from app.models.event import Event  # noqa: E402
from app.models.exception_registration_offer_audit import ExceptionRegistrationOfferAudit  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.staff import StaffAccount  # noqa: E402
