from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.registration import Registration


class WaitlistPromotionOfferStatus(str, enum.Enum):
    OFFERED = "offered"
    PAYMENT_INITIALIZED = "payment_initialized"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    MANUAL_REVIEW = "manual_review"


class WaitlistPromotionOffer(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "waitlist_promotion_offers"
    __table_args__ = (
        UniqueConstraint("registration_id", name="uq_waitlist_promotion_offers_registration_id"),
        UniqueConstraint("payment_id", name="uq_waitlist_promotion_offers_payment_id"),
        Index("ix_waitlist_promotion_offers_status", "status"),
        Index("ix_waitlist_promotion_offers_expires_at", "offer_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("wpo"))
    public_token: Mapped[str] = mapped_column(
        String(26),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: str(ulid.new()),
    )
    registration_id: Mapped[str] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offered_by_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    offer_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[WaitlistPromotionOfferStatus] = mapped_column(
        Enum(WaitlistPromotionOfferStatus, name="waitlist_promotion_offer_status", native_enum=False, length=24),
        nullable=False,
        default=WaitlistPromotionOfferStatus.OFFERED,
        server_default=WaitlistPromotionOfferStatus.OFFERED.value,
    )
    payment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    gateway_checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration: Mapped["Registration"] = relationship(back_populates="waitlist_promotion_offer")
    payment: Mapped["Payment | None"] = relationship(back_populates="waitlist_promotion_offer")


from app.models.payment import Payment  # noqa: E402
from app.models.registration import Registration  # noqa: E402
