"""add inventory tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meter_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("purchased_at", sa.DateTime(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "movement_type",
            sa.Enum("purchase", "reserve", "release", "adjust", name="inventorymovementtype"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["meter_batches.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("stock_movements")
    op.drop_table("meter_batches")
