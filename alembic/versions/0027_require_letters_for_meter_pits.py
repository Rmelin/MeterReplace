"""require letters for meter pit appointments

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE appointments SET letter_required = 1 "
            "WHERE letter_required = 0"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE appointments SET letter_required = 0 "
            "WHERE address_id IN ("
            "SELECT id FROM addresses WHERE buffer_flag = 1"
            ")"
        )
    )
