from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.exception_registration_offer import ExceptionRegistrationOffer
    from app.models.staff import StaffAccount


class ExceptionRegistrationOfferAuditAction(str, enum.Enum):
    ISSUED = "issued"
    REGISTRATION_ATTEMPTED = "registration_attempted"
    REGISTRATION_SUCCEEDED = "registration_succeeded"
    REGISTRATION_REJECTED = "registration_rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ExceptionRegistrationOfferAuditActorType(str, enum.Enum):
    STAFF = "staff"
    PUBLIC = "public"
    SYSTEM = "system"


class ExceptionRegistrationOfferAudit(Base, CreatedAtMixin):
    __tablename__ = "exception_registration_offer_audits"
    __table_args__ = (
        Index("ix_exception_registration_offer_audits_offer_created", "offer_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("exa"))
    offer_id: Mapped[str] = mapped_column(
        ForeignKey("exception_registration_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[ExceptionRegistrationOfferAuditAction] = mapped_column(
        Enum(
            ExceptionRegistrationOfferAuditAction,
            name="exception_registration_offer_audit_action",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    actor_type: Mapped[ExceptionRegistrationOfferAuditActorType] = mapped_column(
        Enum(
            ExceptionRegistrationOfferAuditActorType,
            name="exception_registration_offer_audit_actor_type",
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )
    actor_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    offer: Mapped["ExceptionRegistrationOffer"] = relationship(back_populates="audit_entries")
    actor_staff: Mapped["StaffAccount | None"] = relationship(foreign_keys=[actor_staff_id])


from app.models.exception_registration_offer import ExceptionRegistrationOffer  # noqa: E402
from app.models.staff import StaffAccount  # noqa: E402
