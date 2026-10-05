"""store actual meter change date separately from the planned visit

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("appointments", sa.Column("actual_changed_on", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("appointments") as batch:
        batch.drop_column("actual_changed_on")
