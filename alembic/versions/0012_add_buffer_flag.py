"""add buffer flag

Revision ID: 0012
Revises: 0011
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.add_column(sa.Column("buffer_flag", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.drop_column("buffer_flag")
