"""add async task failures

Revision ID: 20260519_04
Revises: 20260519_03
Create Date: 2026-05-19 22:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_04"
down_revision: str | None = "20260519_03"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


async_task_type = sa.Enum(
    "email",
    "payment",
    "notification",
    "export",
    "other",
    name="async_task_type",
    native_enum=False,
    length=24,
)
async_task_failure_status = sa.Enum(
    "open",
    "acknowledged",
    "resolved",
    name="async_task_failure_status",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    op.create_table(
        "async_task_failures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("task_type", async_task_type, nullable=False),
        sa.Column("failure_category", sa.String(length=64), nullable=False),
        sa.Column("status", async_task_failure_status, server_default="open", nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("registration_id", sa.String(length=36), nullable=True),
        sa.Column("payment_id", sa.String(length=36), nullable=True),
        sa.Column("provider_attempts", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_class", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("payload_metadata", sa.JSON(), nullable=True),
        sa.Column("final_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempt_count > 0", name="attempt_count_positive"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registration_id"], ["registrations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_async_task_failures_status", "async_task_failures", ["status"], unique=False)
    op.create_index("ix_async_task_failures_task_type", "async_task_failures", ["task_type"], unique=False)
    op.create_index("ix_async_task_failures_event_id", "async_task_failures", ["event_id"], unique=False)
    op.create_index("ix_async_task_failures_registration_id", "async_task_failures", ["registration_id"], unique=False)
    op.create_index("ix_async_task_failures_payment_id", "async_task_failures", ["payment_id"], unique=False)
    op.create_index("ix_async_task_failures_final_failed_at", "async_task_failures", ["final_failed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_async_task_failures_final_failed_at", table_name="async_task_failures")
    op.drop_index("ix_async_task_failures_payment_id", table_name="async_task_failures")
    op.drop_index("ix_async_task_failures_registration_id", table_name="async_task_failures")
    op.drop_index("ix_async_task_failures_event_id", table_name="async_task_failures")
    op.drop_index("ix_async_task_failures_task_type", table_name="async_task_failures")
    op.drop_index("ix_async_task_failures_status", table_name="async_task_failures")
    op.drop_table("async_task_failures")
