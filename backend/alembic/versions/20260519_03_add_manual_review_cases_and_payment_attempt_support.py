"""add manual review cases and payment attempt support

Revision ID: 20260519_03
Revises: 20260519_02
Create Date: 2026-05-19 20:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_03"
down_revision: str | None = "20260519_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


manual_review_case_type = sa.Enum(
    "late_payment_success",
    "payment_timeout_requeue",
    "payment_failure_requeue",
    "exception_registration_issue",
    "overflow_policy_cancellation",
    "other",
    name="manual_review_case_type",
    native_enum=False,
    length=40,
)
manual_review_case_status = sa.Enum(
    "open",
    "in_progress",
    "resolved",
    "dismissed",
    name="manual_review_case_status",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.add_column(
        "payments",
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "payments",
        sa.Column("gateway_checkout_url", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "payment_attempt_number_positive",
        "payments",
        "attempt_number > 0",
    )
    for constraint in inspector.get_unique_constraints("payments"):
        if constraint.get("column_names") == ["registration_id"]:
            op.drop_constraint(constraint["name"], "payments", type_="unique")
            break
    op.create_unique_constraint(
        "uq_payments_registration_attempt",
        "payments",
        ["registration_id", "attempt_number"],
    )

    op.add_column(
        "registrations",
        sa.Column("current_payment_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_registrations_current_payment_id_payments",
        "registrations",
        "payments",
        ["current_payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_registrations_current_payment_id"), "registrations", ["current_payment_id"], unique=False)
    op.execute(
        """
        UPDATE registrations
        SET current_payment_id = payments.id
        FROM payments
        WHERE payments.registration_id = registrations.id
        """
    )

    op.create_table(
        "manual_review_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("registration_id", sa.String(length=36), nullable=True),
        sa.Column("payment_id", sa.String(length=36), nullable=True),
        sa.Column("case_type", manual_review_case_type, nullable=False),
        sa.Column("status", manual_review_case_status, server_default="open", nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_by_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by_staff_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_to_staff_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_by_staff_id", sa.String(length=36), nullable=True),
        sa.Column("resolution_action", sa.String(length=64), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_staff_id"], ["staff_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_staff_id"], ["staff_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registration_id"], ["registrations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_staff_id"], ["staff_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manual_review_cases_status", "manual_review_cases", ["status"], unique=False)
    op.create_index("ix_manual_review_cases_event_id", "manual_review_cases", ["event_id"], unique=False)
    op.create_index("ix_manual_review_cases_registration_id", "manual_review_cases", ["registration_id"], unique=False)
    op.create_index("ix_manual_review_cases_payment_id", "manual_review_cases", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_manual_review_cases_payment_id", table_name="manual_review_cases")
    op.drop_index("ix_manual_review_cases_registration_id", table_name="manual_review_cases")
    op.drop_index("ix_manual_review_cases_event_id", table_name="manual_review_cases")
    op.drop_index("ix_manual_review_cases_status", table_name="manual_review_cases")
    op.drop_table("manual_review_cases")

    op.drop_index(op.f("ix_registrations_current_payment_id"), table_name="registrations")
    op.drop_constraint("fk_registrations_current_payment_id_payments", "registrations", type_="foreignkey")
    op.drop_column("registrations", "current_payment_id")

    op.drop_constraint("uq_payments_registration_attempt", "payments", type_="unique")
    op.create_unique_constraint(op.f("uq_payments_registration_id"), "payments", ["registration_id"])
    op.drop_constraint("payment_attempt_number_positive", "payments", type_="check")
    op.drop_column("payments", "gateway_checkout_url")
    op.drop_column("payments", "attempt_number")
