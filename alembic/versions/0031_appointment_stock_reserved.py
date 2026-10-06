"""Track whether an appointment already deducted a meter from stock."""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    # NULL preserves the legacy reservation rules until the next stock change.
    op.add_column("appointments", sa.Column("stock_reserved", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("appointments") as batch:
        batch.drop_column("stock_reserved")
