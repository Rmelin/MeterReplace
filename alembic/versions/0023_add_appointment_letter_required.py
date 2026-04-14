"""add appointment letter required

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.add_column(
            sa.Column("letter_required", sa.Boolean(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_column("letter_required")
