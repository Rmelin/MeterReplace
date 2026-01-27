"""extend appointment status

Revision ID: 0007
Revises: 0006
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'photo_uploaded'")
        op.execute("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'not_home'")
        op.execute("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'needs_reschedule'")
    elif bind.dialect.name == "sqlite":
        with op.batch_alter_table("appointments") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.Enum(
                    "draft",
                    "scheduled",
                    "completed",
                    "cancelled",
                    name="appointmentstatus",
                ),
                type_=sa.String(length=50),
                nullable=False,
            )


def downgrade() -> None:
    pass
