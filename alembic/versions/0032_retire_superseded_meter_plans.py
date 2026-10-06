"""Retain superseded meter plans as history and repair existing future bookings."""

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("appointments") as batch:
        batch.add_column(
            sa.Column(
                "superseded_by_appointment_id",
                sa.Integer(),
                sa.ForeignKey("appointments.id", name="fk_appointment_superseded_by"),
                nullable=True,
            )
        )
    connection = op.get_bind()
    # Repair existing records too; use a frozen SQL version of the reservation
    # rules rather than importing application code into a historical migration.
    finished = (
        connection.execute(
            sa.text("""
        SELECT id, address_id, changed_by_user_id,
               COALESCE(actual_changed_on, date(starts_at)) AS changed_on
        FROM appointments
        WHERE is_manual_task = 0 AND address_id IS NOT NULL
          AND status IN ('COMPLETED', 'CLOSED')
        ORDER BY changed_on DESC, id DESC
    """)
        )
        .mappings()
        .all()
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    for completed in finished:
        pending = (
            connection.execute(
                sa.text("""
            SELECT id, status, stock_reserved, changed_by_user_id
            FROM appointments
            WHERE address_id = :address_id AND id != :id AND is_manual_task = 0
              AND status IN ('SCHEDULED', 'INFORMED', 'NEEDS_RESCHEDULE', 'NOTSCHEDULED')
              AND date(starts_at) >= :changed_on
        """),
                dict(completed),
            )
            .mappings()
            .all()
        )
        for visit in pending:
            reserved = visit["stock_reserved"]
            if reserved is None:
                reserved = visit["status"] in ("SCHEDULED", "INFORMED")
                if visit["status"] == "NEEDS_RESCHEDULE":
                    response_date = connection.execute(
                        sa.text("""
                        SELECT created_at FROM resident_responses
                        WHERE appointment_id = :id AND response_type = 'reschedule_request'
                        ORDER BY created_at DESC, id DESC LIMIT 1
                    """),
                        {"id": visit["id"]},
                    ).scalar()
                    if response_date:
                        reserved = (
                            connection.execute(
                                sa.text("""
                            SELECT id FROM stock_movements WHERE note = :note
                            AND created_at > :response_date LIMIT 1
                        """),
                                {
                                    "note": f"Opgave beholdt på planlagt dag, aftale {visit['id']}",
                                    "response_date": response_date,
                                },
                            ).scalar()
                            is not None
                        )
                    else:
                        reserved = visit["changed_by_user_id"] is not None
            if reserved:
                connection.execute(
                    sa.text("""
                    INSERT INTO stock_movements
                        (movement_type, quantity, created_at, created_by_user_id, note)
                    VALUES ('RELEASE', 1, :now, :user_id, :note)
                """),
                    {
                        "now": now,
                        "user_id": completed["changed_by_user_id"],
                        "note": f"Bortfaldet aftale {visit['id']}: måler skiftet, aftale {completed['id']}",
                    },
                )
            connection.execute(
                sa.text("""
                UPDATE appointments SET status = 'CANCELLED', stock_reserved = 0,
                    superseded_by_appointment_id = :completed_id, letter_required = 0,
                    changed_date = :now, updated_at = :now, changed_by_user_id = :user_id
                WHERE id = :id
            """),
                {
                    "id": visit["id"],
                    "completed_id": completed["id"],
                    "now": now,
                    "user_id": completed["changed_by_user_id"],
                },
            )


def downgrade():
    # Do not recreate redundant reservations or active visits on rollback.
    # Older versions cannot read CANCELLED; keep these plans inactive instead.
    op.execute(
        "UPDATE appointments SET status = 'NOTSCHEDULED' WHERE status = 'CANCELLED'"
    )
    with op.batch_alter_table("appointments") as batch:
        batch.drop_column("superseded_by_appointment_id")
