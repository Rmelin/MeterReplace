"""add appointment photos

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointment_photos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("appointment_id", sa.Integer, nullable=False),
        sa.Column("address_id", sa.Integer, nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("appointment_photos")
