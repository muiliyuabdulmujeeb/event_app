"""add staff event authorizations

Revision ID: 20260518_01
Revises: 20260517_01
Create Date: 2026-05-18 09:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260518_01"
down_revision: str | None = "20260517_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_event_authorizations",
        sa.Column("staff_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("can_manage_exception_offers", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_change_overflow_rule", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_manage_manual_reviews", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_requeue_registrations", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("granted_by_staff_id", sa.String(length=36), nullable=False),
        sa.Column("revoked_by_staff_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_staff_event_authorizations_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_staff_event_authorizations_granted_by_staff_id_staff_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_staff_event_authorizations_revoked_by_staff_id_staff_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_staff_event_authorizations_staff_id_staff_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("staff_id", "event_id", name=op.f("pk_staff_event_authorizations")),
    )
    op.create_index(
        op.f("ix_staff_event_authorizations_event_id"),
        "staff_event_authorizations",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_event_authorizations_granted_by_staff_id"),
        "staff_event_authorizations",
        ["granted_by_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_event_authorizations_revoked_by_staff_id"),
        "staff_event_authorizations",
        ["revoked_by_staff_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_staff_event_authorizations_revoked_by_staff_id"), table_name="staff_event_authorizations")
    op.drop_index(op.f("ix_staff_event_authorizations_granted_by_staff_id"), table_name="staff_event_authorizations")
    op.drop_index(op.f("ix_staff_event_authorizations_event_id"), table_name="staff_event_authorizations")
    op.drop_table("staff_event_authorizations")
