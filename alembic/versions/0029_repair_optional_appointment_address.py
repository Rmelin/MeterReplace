"""repair legacy databases that still require a meter visit address

Revision ID: 0029
Revises: 0028
"""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("appointments")
    address_column = next(column for column in columns if column["name"] == "address_id")
    if not address_column["nullable"]:
        with op.batch_alter_table("appointments") as batch_op:
            batch_op.alter_column("address_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Nullable address_id is already required by revision 0018. Keep that schema.
    pass
