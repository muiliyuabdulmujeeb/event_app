"""add exception registration offers

Revision ID: 20260519_01
Revises: 20260518_01
Create Date: 2026-05-19 09:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_01"
down_revision: str | None = "20260518_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


exception_offer_status = sa.Enum(
    "issued",
    "used",
    "expired",
    "revoked",
    name="exception_registration_offer_status",
    native_enum=False,
    length=16,
)
exception_offer_audit_action = sa.Enum(
    "issued",
    "registration_attempted",
    "registration_succeeded",
    "registration_rejected",
    "revoked",
    "expired",
    name="exception_registration_offer_audit_action",
    native_enum=False,
    length=32,
)
exception_offer_audit_actor_type = sa.Enum(
    "staff",
    "public",
    "system",
    name="exception_registration_offer_audit_actor_type",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    exception_offer_status.create(op.get_bind(), checkfirst=True)
    exception_offer_audit_action.create(op.get_bind(), checkfirst=True)
    exception_offer_audit_actor_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "exception_registration_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("public_token", sa.String(length=26), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("issued_by_staff_id", sa.String(length=36), nullable=False),
        sa.Column("target_email", sa.String(length=320), nullable=False),
        sa.Column("target_first_name", sa.String(length=120), nullable=True),
        sa.Column("target_last_name", sa.String(length=120), nullable=True),
        sa.Column("source_reg_id", sa.String(length=18), nullable=True),
        sa.Column("payment_waived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("capacity_override", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", exception_offer_status, server_default="issued", nullable=False),
        sa.Column("used_registration_id", sa.String(length=36), nullable=True),
        sa.Column("gateway_checkout_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_exception_registration_offers_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_exception_registration_offers_issued_by_staff_id_staff_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["used_registration_id"],
            ["registrations.id"],
            name=op.f("fk_exception_registration_offers_used_registration_id_registrations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exception_registration_offers")),
        sa.UniqueConstraint("public_token", name=op.f("uq_exception_registration_offers_public_token")),
        sa.UniqueConstraint("used_registration_id", name=op.f("uq_exception_registration_offers_used_registration_id")),
    )
    op.create_index(
        op.f("ix_exception_registration_offers_public_token"),
        "exception_registration_offers",
        ["public_token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_exception_registration_offers_event_id"),
        "exception_registration_offers",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_registration_offers_event_status"),
        "exception_registration_offers",
        ["event_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_registration_offers_issued_by_staff_id"),
        "exception_registration_offers",
        ["issued_by_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_registration_offers_target_email"),
        "exception_registration_offers",
        ["target_email"],
        unique=False,
    )

    op.create_table(
        "exception_registration_offer_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.String(length=36), nullable=False),
        sa.Column("action", exception_offer_audit_action, nullable=False),
        sa.Column("actor_type", exception_offer_audit_actor_type, nullable=False),
        sa.Column("actor_staff_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_staff_id"],
            ["staff_accounts.id"],
            name=op.f("fk_exception_registration_offer_audits_actor_staff_id_staff_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["exception_registration_offers.id"],
            name=op.f("fk_exception_registration_offer_audits_offer_id_exception_registration_offers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exception_registration_offer_audits")),
    )
    op.create_index(
        op.f("ix_exception_registration_offer_audits_actor_staff_id"),
        "exception_registration_offer_audits",
        ["actor_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_registration_offer_audits_offer_id"),
        "exception_registration_offer_audits",
        ["offer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_registration_offer_audits_offer_created"),
        "exception_registration_offer_audits",
        ["offer_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_exception_registration_offer_audits_offer_created"), table_name="exception_registration_offer_audits")
    op.drop_index(op.f("ix_exception_registration_offer_audits_offer_id"), table_name="exception_registration_offer_audits")
    op.drop_index(op.f("ix_exception_registration_offer_audits_actor_staff_id"), table_name="exception_registration_offer_audits")
    op.drop_table("exception_registration_offer_audits")

    op.drop_index(op.f("ix_exception_registration_offers_target_email"), table_name="exception_registration_offers")
    op.drop_index(op.f("ix_exception_registration_offers_issued_by_staff_id"), table_name="exception_registration_offers")
    op.drop_index(op.f("ix_exception_registration_offers_event_status"), table_name="exception_registration_offers")
    op.drop_index(op.f("ix_exception_registration_offers_event_id"), table_name="exception_registration_offers")
    op.drop_index(op.f("ix_exception_registration_offers_public_token"), table_name="exception_registration_offers")
    op.drop_table("exception_registration_offers")

    exception_offer_audit_actor_type.drop(op.get_bind(), checkfirst=True)
    exception_offer_audit_action.drop(op.get_bind(), checkfirst=True)
    exception_offer_status.drop(op.get_bind(), checkfirst=True)
