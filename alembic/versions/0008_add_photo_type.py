"""add photo type

Revision ID: 0008
Revises: 0007
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("appointment_photos") as batch_op:
        batch_op.add_column(
            sa.Column("photo_type", sa.String(length=20), nullable=False, server_default="both")
        )


def downgrade() -> None:
    with op.batch_alter_table("appointment_photos") as batch_op:
        batch_op.drop_column("photo_type")
