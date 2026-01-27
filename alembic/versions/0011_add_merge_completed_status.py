"""add merge completed status

Revision ID: 0011
Revises: 0010
Create Date: 2026-01-20
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'merge_completed'")


def downgrade() -> None:
    pass
