from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.registration import BatchRegistration, Registration
    from app.models.waitlist_promotion_offer import WaitlistPromotionOffer


class PaymentGateway(str, enum.Enum):
    PAYSTACK = "paystack"
    SQUAD = "squad"
    MOCK = "mock"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class Payment(Base, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("num_nonnulls(registration_id, batch_id) = 1", name="single_payment_owner"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("pay"))
    gateway: Mapped[PaymentGateway] = mapped_column(
        Enum(PaymentGateway, name="payment_gateway", native_enum=False, length=16),
        nullable=False,
    )
    payment_reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN", server_default="NGN")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=16),
        nullable=False,
    )
    registration_id: Mapped[str | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("batch_registrations.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    registration: Mapped["Registration | None"] = relationship(back_populates="payment")
    batch_registration: Mapped["BatchRegistration | None"] = relationship(back_populates="payment")
    waitlist_promotion_offer: Mapped["WaitlistPromotionOffer | None"] = relationship(
        back_populates="payment",
        uselist=False,
    )


from app.models.registration import BatchRegistration, Registration  # noqa: E402
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer  # noqa: E402
