from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, new_id

if TYPE_CHECKING:
    from app.models.registration import Registration
    from app.models.staff import StaffAccount


class StaffNotification(Base, CreatedAtMixin):
    __tablename__ = "staff_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("snt"))
    staff_id: Mapped[str] = mapped_column(
        ForeignKey("staff_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    staff: Mapped["StaffAccount"] = relationship(back_populates="notifications")


class UserNotification(Base, CreatedAtMixin):
    __tablename__ = "user_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: new_id("unt"))
    reg_id: Mapped[str] = mapped_column(
        ForeignKey("registrations.reg_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_seen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    registration: Mapped["Registration"] = relationship(
        back_populates="user_notifications",
        primaryjoin="UserNotification.reg_id == Registration.reg_id",
    )


from app.models.registration import Registration  # noqa: E402
