"""Store a resident's answers together in one inbox entry."""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resident_responses") as batch:
        batch.add_column(sa.Column("meter_pit_answer", sa.String(3), nullable=True))
        batch.add_column(sa.Column("meter_pit_location", sa.String(255), nullable=True))
        batch.add_column(sa.Column("time_preference", sa.Text(), nullable=True))
        batch.add_column(sa.Column("contact_name", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resident_responses") as batch:
        batch.drop_column("contact_name")
        batch.drop_column("time_preference")
        batch.drop_column("meter_pit_location")
        batch.drop_column("meter_pit_answer")
