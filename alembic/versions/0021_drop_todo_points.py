"""drop todo points

Revision ID: 0021
Revises: 0020
Create Date: 2026-03-03
"""

from alembic import op
from sqlalchemy import inspect

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "todo_points" in inspector.get_table_names():
        op.drop_table("todo_points")
    if bind.dialect.name != "sqlite":
        op.execute("DROP TYPE IF EXISTS todopointstatus")


def downgrade() -> None:
    pass
