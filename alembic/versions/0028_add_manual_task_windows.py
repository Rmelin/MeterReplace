"""distinguish VVS tasks from meter visits and store their time window

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.add_column(sa.Column("is_manual_task", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("time_window", sa.String(length=20), nullable=False, server_default="exact"))
        batch_op.add_column(sa.Column("task_address_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_appointments_task_address", "addresses", ["task_address_id"], ["id"])
    op.execute(sa.text("UPDATE appointments SET is_manual_task = 1, letter_required = 0 WHERE address_id IS NULL"))


def downgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_constraint("fk_appointments_task_address", type_="foreignkey")
        batch_op.drop_column("task_address_id")
        batch_op.drop_column("time_window")
        batch_op.drop_column("is_manual_task")
