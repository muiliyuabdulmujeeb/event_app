"""add refund requests and registration cancellation history

Revision ID: 20260519_02
Revises: 20260519_01
Create Date: 2026-05-19 16:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_02"
down_revision: str | None = "20260519_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


refund_request_status = sa.Enum(
    "requested",
    "approved",
    "rejected",
    "completed",
    name="refund_request_status",
    native_enum=False,
    length=16,
)
refund_requested_by = sa.Enum(
    "public",
    "admin",
    "system",
    name="refund_requested_by",
    native_enum=False,
    length=16,
)
cancellation_reason = sa.Enum(
    "user_cancelled",
    "overflow_rule_changed",
    name="cancellation_reason",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.add_column(
        "registrations",
        sa.Column("was_waitlisted", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "registrations",
        sa.Column("previous_waitlist_position", sa.Integer(), nullable=True),
    )
    op.add_column(
        "registrations",
        sa.Column("cancellation_reason", cancellation_reason, nullable=True),
    )
    op.create_check_constraint(
        "previous_waitlist_position_positive",
        "registrations",
        "previous_waitlist_position IS NULL OR previous_waitlist_position > 0",
    )

    op.create_table(
        "refund_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("registration_id", sa.String(length=36), nullable=False),
        sa.Column("status", refund_request_status, server_default="requested", nullable=False),
        sa.Column("requested_by", refund_requested_by, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_by_staff_id", sa.String(length=36), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["processed_by_staff_id"], ["staff_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registration_id"], ["registrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refund_requests_registration_id", "refund_requests", ["registration_id"], unique=False)
    op.create_index("ix_refund_requests_requested_at", "refund_requests", ["requested_at"], unique=False)
    op.create_index("ix_refund_requests_status", "refund_requests", ["status"], unique=False)
    op.create_index(op.f("ix_refund_requests_processed_by_staff_id"), "refund_requests", ["processed_by_staff_id"], unique=False)

    op.execute(
        """
        INSERT INTO refund_requests (
            id,
            registration_id,
            status,
            requested_by,
            reason,
            requested_at,
            processed_by_staff_id,
            processed_at,
            resolution_notes,
            created_at,
            updated_at
        )
        SELECT
            'rrq_' || substr(md5(registrations.id || registrations.reg_id || registrations.state), 1, 32),
            registrations.id,
            CASE
                WHEN registrations.state = 'refund_requested' THEN 'requested'
                WHEN registrations.state = 'refunded' THEN 'completed'
            END,
            'system',
            'Migrated from legacy registration refund state.',
            COALESCE(registrations.updated_at, registrations.registered_at, now()),
            NULL,
            CASE
                WHEN registrations.state = 'refunded'
                    THEN COALESCE(registrations.updated_at, registrations.registered_at, now())
                ELSE NULL
            END,
            CASE
                WHEN registrations.state = 'refunded'
                    THEN 'Migrated from legacy registration refund state.'
                ELSE NULL
            END,
            COALESCE(registrations.updated_at, registrations.registered_at, now()),
            COALESCE(registrations.updated_at, registrations.registered_at, now())
        FROM registrations
        WHERE registrations.state IN ('refund_requested', 'refunded')
        """
    )

    op.execute(
        """
        UPDATE registrations
        SET state = 'cancelled'
        WHERE state IN ('refund_requested', 'refunded')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE registrations
        SET state = CASE
            WHEN refund_requests.status = 'requested' THEN 'refund_requested'
            WHEN refund_requests.status = 'completed' THEN 'refunded'
            ELSE registrations.state
        END
        FROM refund_requests
        WHERE refund_requests.registration_id = registrations.id
          AND refund_requests.status IN ('requested', 'completed')
        """
    )
    op.drop_index(op.f("ix_refund_requests_processed_by_staff_id"), table_name="refund_requests")
    op.drop_index("ix_refund_requests_status", table_name="refund_requests")
    op.drop_index("ix_refund_requests_requested_at", table_name="refund_requests")
    op.drop_index("ix_refund_requests_registration_id", table_name="refund_requests")
    op.drop_table("refund_requests")
    op.drop_constraint("previous_waitlist_position_positive", "registrations", type_="check")
    op.drop_column("registrations", "cancellation_reason")
    op.drop_column("registrations", "previous_waitlist_position")
    op.drop_column("registrations", "was_waitlisted")
