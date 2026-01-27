"""add appointments

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("address_id", sa.Integer, nullable=False),
        sa.Column("contractor_id", sa.Integer, nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "scheduled", "completed", "cancelled", name="appointmentstatus"),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("changed_date", sa.DateTime(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
        sa.ForeignKeyConstraint(["contractor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("appointments")
