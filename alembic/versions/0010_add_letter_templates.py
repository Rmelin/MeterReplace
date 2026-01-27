"""add letter templates

Revision ID: 0010
Revises: 0009
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "letter_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("logo_path", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("letter_templates")
