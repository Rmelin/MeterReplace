"""make resident links reusable

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resident_links") as batch_op:
        batch_op.add_column(
            sa.Column("appointment_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_resident_links_appointment",
            "appointments",
            ["appointment_id"],
            ["id"],
        )
    op.create_index(
        "ix_resident_links_address_appointment_active",
        "resident_links",
        ["address_id", "appointment_id", "active"],
    )

    with op.batch_alter_table("resident_responses") as batch_op:
        batch_op.add_column(
            sa.Column("resident_link_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("answer", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("request_id", sa.String(length=64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_resident_responses_link",
            "resident_links",
            ["resident_link_id"],
            ["id"],
        )
    op.create_index(
        "ix_resident_responses_link_type_created",
        "resident_responses",
        ["resident_link_id", "response_type", "created_at"],
    )
    op.create_index(
        "ux_resident_responses_request_id",
        "resident_responses",
        ["request_id"],
        unique=True,
    )

    op.execute(
        sa.text(
            """
            UPDATE resident_responses
            SET answer = CASE response_type
                WHEN 'buffer_note' THEN 'yes'
                WHEN 'confirm_time' THEN 'yes'
                WHEN 'reschedule_request' THEN 'no'
                ELSE NULL
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resident_responses
            SET resident_link_id = (
                SELECT resident_links.id
                FROM resident_links
                WHERE resident_links.address_id = resident_responses.address_id
                  AND resident_links.created_at <= resident_responses.created_at
                ORDER BY resident_links.created_at DESC, resident_links.id DESC
                LIMIT 1
            )
            WHERE resident_link_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resident_links
            SET appointment_id = (
                SELECT resident_responses.appointment_id
                FROM resident_responses
                WHERE resident_responses.resident_link_id = resident_links.id
                  AND resident_responses.appointment_id IS NOT NULL
                ORDER BY resident_responses.created_at DESC, resident_responses.id DESC
                LIMIT 1
            )
            WHERE appointment_id IS NULL
            """
        )
    )
    # Existing inactive links were consumed submissions; there was no revoke feature.
    op.execute(sa.text("UPDATE resident_links SET active = 1"))


def downgrade() -> None:
    op.drop_index(
        "ux_resident_responses_request_id",
        table_name="resident_responses",
    )
    op.drop_index(
        "ix_resident_responses_link_type_created",
        table_name="resident_responses",
    )
    with op.batch_alter_table("resident_responses") as batch_op:
        batch_op.drop_constraint(
            "fk_resident_responses_link",
            type_="foreignkey",
        )
        batch_op.drop_column("request_id")
        batch_op.drop_column("answer")
        batch_op.drop_column("resident_link_id")
    op.drop_index(
        "ix_resident_links_address_appointment_active",
        table_name="resident_links",
    )
    with op.batch_alter_table("resident_links") as batch_op:
        batch_op.drop_constraint(
            "fk_resident_links_appointment",
            type_="foreignkey",
        )
        batch_op.drop_column("appointment_id")
