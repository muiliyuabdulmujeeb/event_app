"""add waitlist promotion offers

Revision ID: 20260517_01
Revises: 20260426_02
Create Date: 2026-05-17 12:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_01"
down_revision: str | None = "20260426_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waitlist_promotion_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("public_token", sa.String(length=26), nullable=False),
        sa.Column("registration_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("offered_by_staff_id", sa.String(length=36), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "offered",
                "payment_initialized",
                "paid",
                "failed",
                "expired",
                "cancelled",
                "manual_review",
                name="waitlist_promotion_offer_status",
                native_enum=False,
                length=24,
            ),
            server_default="offered",
            nullable=False,
        ),
        sa.Column("payment_id", sa.String(length=36), nullable=True),
        sa.Column("gateway_checkout_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_waitlist_promotion_offers_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["offered_by_staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_waitlist_promotion_offers_offered_by_staff_id_staff_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_waitlist_promotion_offers_payment_id_payments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["registrations.id"],
            name=op.f("fk_waitlist_promotion_offers_registration_id_registrations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waitlist_promotion_offers")),
        sa.UniqueConstraint("payment_id", name="uq_waitlist_promotion_offers_payment_id"),
        sa.UniqueConstraint("public_token", name=op.f("uq_waitlist_promotion_offers_public_token")),
        sa.UniqueConstraint("registration_id", name="uq_waitlist_promotion_offers_registration_id"),
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_event_id"),
        "waitlist_promotion_offers",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_expires_at"),
        "waitlist_promotion_offers",
        ["offer_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_offered_by_staff_id"),
        "waitlist_promotion_offers",
        ["offered_by_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_public_token"),
        "waitlist_promotion_offers",
        ["public_token"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_registration_id"),
        "waitlist_promotion_offers",
        ["registration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waitlist_promotion_offers_status"),
        "waitlist_promotion_offers",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_waitlist_promotion_offers_status"), table_name="waitlist_promotion_offers")
    op.drop_index(op.f("ix_waitlist_promotion_offers_registration_id"), table_name="waitlist_promotion_offers")
    op.drop_index(op.f("ix_waitlist_promotion_offers_public_token"), table_name="waitlist_promotion_offers")
    op.drop_index(op.f("ix_waitlist_promotion_offers_offered_by_staff_id"), table_name="waitlist_promotion_offers")
    op.drop_index(op.f("ix_waitlist_promotion_offers_expires_at"), table_name="waitlist_promotion_offers")
    op.drop_index(op.f("ix_waitlist_promotion_offers_event_id"), table_name="waitlist_promotion_offers")
    op.drop_table("waitlist_promotion_offers")
