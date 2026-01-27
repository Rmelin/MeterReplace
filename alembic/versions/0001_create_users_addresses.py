"""create users and addresses

Revision ID: 0001
Revises: 
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(length=150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("admin", "vvs", name="userrole"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("street", sa.String(length=200), nullable=False),
        sa.Column("house_no", sa.String(length=50), nullable=False),
        sa.Column("zip", sa.String(length=20), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("addresses")
    op.drop_table("users")
