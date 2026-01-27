"""add resident contact fields

Revision ID: 0015
Revises: 0014
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.add_column(sa.Column("resident_phone", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("resident_email", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.drop_column("resident_email")
        batch_op.drop_column("resident_phone")
