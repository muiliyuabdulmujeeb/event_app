"""initial schema

Revision ID: 20260426_01
Revises:
Create Date: 2026-04-26 14:40:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_01"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


staff_role = sa.Enum("admin", "staff", name="staff_role", native_enum=False, length=16)
staff_access_mode = sa.Enum(
    "all_events",
    "selected_events",
    name="staff_access_mode",
    native_enum=False,
    length=24,
)
event_state = sa.Enum(
    "draft",
    "published",
    "completed",
    "cancelled",
    name="event_state",
    native_enum=False,
    length=32,
)
overflow_rule = sa.Enum(
    "hard_rejection",
    "waitlist",
    name="overflow_rule",
    native_enum=False,
    length=32,
)
field_type = sa.Enum("text", "number", "date", "phone", "email", name="field_type", native_enum=False, length=16)
registration_state = sa.Enum(
    "pending_payment",
    "confirmed",
    "failed",
    "cancelled",
    "refund_requested",
    "refunded",
    "waitlisted",
    name="registration_state",
    native_enum=False,
    length=24,
)
payment_gateway = sa.Enum(
    "paystack",
    "squad",
    "mock",
    name="payment_gateway",
    native_enum=False,
    length=16,
)
payment_status = sa.Enum(
    "pending",
    "successful",
    "failed",
    name="payment_status",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "staff_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", staff_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_accounts")),
        sa.UniqueConstraint("email", name=op.f("uq_staff_accounts_email")),
    )
    op.create_index(op.f("ix_staff_accounts_email"), "staff_accounts", ["email"], unique=False)

    op.create_table(
        "staff_access_mode",
        sa.Column("staff_id", sa.String(length=36), nullable=False),
        sa.Column("mode", staff_access_mode, server_default="all_events", nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"], name=op.f("fk_staff_access_mode_staff_id_staff_accounts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("staff_id", name=op.f("pk_staff_access_mode")),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("prefix", sa.String(length=5), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("is_free", sa.Boolean(), sa.Computed("price = 0", persisted=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("overflow_rule", overflow_rule, nullable=False),
        sa.Column("state", event_state, nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("capacity IS NULL OR capacity > 0", name=op.f("ck_events_capacity_positive")),
        sa.CheckConstraint("prefix ~ '^[A-Z0-9]{2,5}$'", name=op.f("ck_events_prefix_format")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_events_price_non_negative")),
        sa.ForeignKeyConstraint(["created_by"], ["staff_accounts.id"], name=op.f("fk_events_created_by_staff_accounts"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("prefix", name=op.f("uq_events_prefix")),
    )
    op.create_index(op.f("ix_events_created_by"), "events", ["created_by"], unique=False)
    op.create_index("ix_events_event_date", "events", ["event_date"], unique=False)
    op.create_index("ix_events_state", "events", ["state"], unique=False)

    op.create_table(
        "staff_event_access",
        sa.Column("staff_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_staff_event_access_event_id_events"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"], name=op.f("fk_staff_event_access_staff_id_staff_accounts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("staff_id", "event_id", name=op.f("pk_staff_event_access")),
    )

    op.create_table(
        "event_field_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("field_type", field_type, nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_event_field_definitions_display_order_positive")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_event_field_definitions_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_field_definitions")),
        sa.UniqueConstraint("event_id", "display_order", name="uq_event_field_definitions_order"),
    )
    op.create_index(op.f("ix_event_field_definitions_event_id"), "event_field_definitions", ["event_id"], unique=False)

    op.create_table(
        "batch_registrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("submitter_name", sa.String(length=255), nullable=False),
        sa.Column("submitter_email", sa.String(length=320), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("payment_reference", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total_amount >= 0", name=op.f("ck_batch_registrations_total_amount_non_negative")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_batch_registrations_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_registrations")),
    )
    op.create_index(op.f("ix_batch_registrations_event_id"), "batch_registrations", ["event_id"], unique=False)

    op.create_table(
        "registrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("reg_id", sa.String(length=18), nullable=False),
        sa.Column("state", registration_state, nullable=False),
        sa.Column("is_checked_in", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waitlist_position", sa.Integer(), nullable=True),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reg_id ~ '^[A-Z0-9]{2,5}-[0-9]{4}-[A-Z0-9]{6}$'", name=op.f("ck_registrations_reg_id_format")),
        sa.CheckConstraint("waitlist_position IS NULL OR waitlist_position > 0", name=op.f("ck_registrations_waitlist_position_positive")),
        sa.ForeignKeyConstraint(["batch_id"], ["batch_registrations.id"], name=op.f("fk_registrations_batch_id_batch_registrations"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_registrations_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registrations")),
        sa.UniqueConstraint("reg_id", name=op.f("uq_registrations_reg_id")),
    )
    op.create_index(op.f("ix_registrations_batch_id"), "registrations", ["batch_id"], unique=False)
    op.create_index(op.f("ix_registrations_email"), "registrations", ["email"], unique=False)
    op.create_index(op.f("ix_registrations_event_id"), "registrations", ["event_id"], unique=False)
    op.create_index(op.f("ix_registrations_reg_id"), "registrations", ["reg_id"], unique=False)
    op.create_index("ix_registrations_registered_at", "registrations", ["registered_at"], unique=False)
    op.create_index("ix_registrations_state", "registrations", ["state"], unique=False)
    op.create_index(
        "ix_registrations_waitlist_queue",
        "registrations",
        ["event_id", "state", "waitlist_position"],
        unique=False,
    )

    op.create_table(
        "registration_field_values",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("registration_id", sa.String(length=36), nullable=False),
        sa.Column("field_definition_id", sa.String(length=36), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["field_definition_id"], ["event_field_definitions.id"], name=op.f("fk_registration_field_values_field_definition_id_event_field_definitions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registration_id"], ["registrations.id"], name=op.f("fk_registration_field_values_registration_id_registrations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_field_values")),
        sa.UniqueConstraint("registration_id", "field_definition_id", name="uq_registration_field_values_registration_field"),
    )
    op.create_index(op.f("ix_registration_field_values_field_definition_id"), "registration_field_values", ["field_definition_id"], unique=False)
    op.create_index(op.f("ix_registration_field_values_registration_id"), "registration_field_values", ["registration_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("gateway", payment_gateway, nullable=False),
        sa.Column("payment_reference", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="NGN", nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("registration_id", sa.String(length=36), nullable=True),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_payments_amount_non_negative")),
        sa.CheckConstraint("num_nonnulls(registration_id, batch_id) = 1", name=op.f("ck_payments_single_payment_owner")),
        sa.ForeignKeyConstraint(["batch_id"], ["batch_registrations.id"], name=op.f("fk_payments_batch_id_batch_registrations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registration_id"], ["registrations.id"], name=op.f("fk_payments_registration_id_registrations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("batch_id", name=op.f("uq_payments_batch_id")),
        sa.UniqueConstraint("payment_reference", name=op.f("uq_payments_payment_reference")),
        sa.UniqueConstraint("registration_id", name=op.f("uq_payments_registration_id")),
    )
    op.create_index(op.f("ix_payments_payment_reference"), "payments", ["payment_reference"], unique=False)

    op.create_table(
        "staff_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("staff_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"], name=op.f("fk_staff_notifications_staff_id_staff_accounts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_notifications")),
    )
    op.create_index(op.f("ix_staff_notifications_staff_id"), "staff_notifications", ["staff_id"], unique=False)

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reg_id", sa.String(length=18), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_seen", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["reg_id"], ["registrations.reg_id"], name=op.f("fk_user_notifications_reg_id_registrations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_notifications")),
    )
    op.create_index(op.f("ix_user_notifications_reg_id"), "user_notifications", ["reg_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_notifications_reg_id"), table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_index(op.f("ix_staff_notifications_staff_id"), table_name="staff_notifications")
    op.drop_table("staff_notifications")
    op.drop_index(op.f("ix_payments_payment_reference"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_registration_field_values_registration_id"), table_name="registration_field_values")
    op.drop_index(op.f("ix_registration_field_values_field_definition_id"), table_name="registration_field_values")
    op.drop_table("registration_field_values")
    op.drop_index("ix_registrations_waitlist_queue", table_name="registrations")
    op.drop_index("ix_registrations_state", table_name="registrations")
    op.drop_index("ix_registrations_registered_at", table_name="registrations")
    op.drop_index(op.f("ix_registrations_reg_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_event_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_email"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_batch_id"), table_name="registrations")
    op.drop_table("registrations")
    op.drop_index(op.f("ix_batch_registrations_event_id"), table_name="batch_registrations")
    op.drop_table("batch_registrations")
    op.drop_index(op.f("ix_event_field_definitions_event_id"), table_name="event_field_definitions")
    op.drop_table("event_field_definitions")
    op.drop_table("staff_event_access")
    op.drop_index("ix_events_state", table_name="events")
    op.drop_index("ix_events_event_date", table_name="events")
    op.drop_index(op.f("ix_events_created_by"), table_name="events")
    op.drop_table("events")
    op.drop_table("staff_access_mode")
    op.drop_index(op.f("ix_staff_accounts_email"), table_name="staff_accounts")
    op.drop_table("staff_accounts")
