"""make appointment address optional

Revision ID: 0018
Revises: 0017
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.alter_column(
            "address_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.alter_column(
            "address_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
