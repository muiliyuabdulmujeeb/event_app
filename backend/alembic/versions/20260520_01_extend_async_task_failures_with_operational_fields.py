"""extend async task failures with operational fields

Revision ID: 20260520_01
Revises: 20260519_04
Create Date: 2026-05-20 15:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_01"
down_revision: str | None = "20260519_04"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("async_task_failures", sa.Column("acknowledged_by_staff_id", sa.String(length=36), nullable=True))
    op.add_column("async_task_failures", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("async_task_failures", sa.Column("resolved_by_staff_id", sa.String(length=36), nullable=True))
    op.add_column("async_task_failures", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("async_task_failures", sa.Column("resolution_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_async_task_failures_acknowledged_by_staff_id",
        "async_task_failures",
        "staff_accounts",
        ["acknowledged_by_staff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_async_task_failures_resolved_by_staff_id",
        "async_task_failures",
        "staff_accounts",
        ["resolved_by_staff_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_async_task_failures_resolved_by_staff_id",
        "async_task_failures",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_async_task_failures_acknowledged_by_staff_id",
        "async_task_failures",
        type_="foreignkey",
    )
    op.drop_column("async_task_failures", "resolution_notes")
    op.drop_column("async_task_failures", "resolved_at")
    op.drop_column("async_task_failures", "resolved_by_staff_id")
    op.drop_column("async_task_failures", "acknowledged_at")
    op.drop_column("async_task_failures", "acknowledged_by_staff_id")
