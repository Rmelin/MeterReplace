"""add resident message status

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resident_responses") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mailbox_status",
                sa.Enum(
                    "NEW",
                    "TODO",
                    "READ",
                    "ARCHIVED",
                    name="residentmessagestatus",
                    native_enum=False,
                    create_constraint=False,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("mailbox_status_updated_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "mailbox_status_updated_by_user_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_resident_responses_mailbox_status_user",
            "users",
            ["mailbox_status_updated_by_user_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE resident_responses
            SET mailbox_status = 'NEW',
                mailbox_status_updated_at = created_at
            WHERE message IS NOT NULL AND trim(message) != ''
            """
        )
    )
    op.create_index(
        "ix_resident_responses_mailbox_status_created_at",
        "resident_responses",
        ["mailbox_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resident_responses_mailbox_status_created_at",
        table_name="resident_responses",
    )
    with op.batch_alter_table("resident_responses") as batch_op:
        batch_op.drop_constraint(
            "fk_resident_responses_mailbox_status_user",
            type_="foreignkey",
        )
        batch_op.drop_column("mailbox_status_updated_by_user_id")
        batch_op.drop_column("mailbox_status_updated_at")
        batch_op.drop_column("mailbox_status")
