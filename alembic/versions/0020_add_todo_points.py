"""add todo points

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "todo_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "resolved", "needs_clarification", name="todopointstatus"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("todo_points")
    op.execute("DROP TYPE IF EXISTS todopointstatus")
