"""add address coordinates

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
