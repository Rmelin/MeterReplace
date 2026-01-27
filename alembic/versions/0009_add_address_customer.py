"""add address customer fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.add_column(sa.Column("customer_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("customer_email", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("customer_email")
        batch_op.drop_column("customer_name")
