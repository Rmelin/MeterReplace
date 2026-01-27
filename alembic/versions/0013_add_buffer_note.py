"""add buffer note

Revision ID: 0013
Revises: 0012
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.add_column(sa.Column("buffer_note", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("addresses") as batch_op:
        batch_op.drop_column("buffer_note")
