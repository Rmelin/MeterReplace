"""add resident links and responses

Revision ID: 0014
Revises: 0013
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resident_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("address_id", sa.Integer, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
    )
    op.create_table(
        "resident_responses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("address_id", sa.Integer, nullable=False),
        sa.Column("appointment_id", sa.Integer, nullable=True),
        sa.Column("response_type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
    )


def downgrade() -> None:
    op.drop_table("resident_responses")
    op.drop_table("resident_links")
