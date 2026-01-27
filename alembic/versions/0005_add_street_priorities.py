"""add street priorities

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "street_priorities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("street", sa.String(length=200), nullable=False, unique=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("street_priorities")
