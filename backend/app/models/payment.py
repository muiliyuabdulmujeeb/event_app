from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.manual_review_case import ManualReviewCase
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
        CheckConstraint("attempt_number > 0", name="payment_attempt_number_positive"),
        CheckConstraint("num_nonnulls(registration_id, batch_id) = 1", name="single_payment_owner"),
        UniqueConstraint("registration_id", "attempt_number", name="uq_payments_registration_attempt"),
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
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    registration_id: Mapped[str | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=True,
    )
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("batch_registrations.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gateway_checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration: Mapped["Registration | None"] = relationship(
        back_populates="payments",
        foreign_keys=[registration_id],
        overlaps="payment",
    )
    batch_registration: Mapped["BatchRegistration | None"] = relationship(back_populates="payment")
    waitlist_promotion_offer: Mapped["WaitlistPromotionOffer | None"] = relationship(
        back_populates="payment",
        uselist=False,
    )
    manual_review_cases: Mapped[list["ManualReviewCase"]] = relationship(back_populates="payment")


from app.models.manual_review_case import ManualReviewCase  # noqa: E402
from app.models.registration import BatchRegistration, Registration  # noqa: E402
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer  # noqa: E402
