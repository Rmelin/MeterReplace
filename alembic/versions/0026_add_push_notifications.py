"""add push notifications

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("expiration_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user_disabled",
        "push_subscriptions",
        ["user_id", "disabled_at"],
    )
    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_response_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["resident_response_id"], ["resident_responses.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["push_subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resident_response_id",
            "subscription_id",
            name="uq_push_delivery_response_subscription",
        ),
    )
    op.create_index(
        "ix_push_deliveries_pending",
        "push_deliveries",
        ["sent_at", "failed_at", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_push_deliveries_pending", table_name="push_deliveries")
    op.drop_table("push_deliveries")
    op.drop_index(
        "ix_push_subscriptions_user_disabled",
        table_name="push_subscriptions",
    )
    op.drop_table("push_subscriptions")
