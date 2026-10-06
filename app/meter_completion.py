from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.timeutils import utc_now


def has_reserved_meter(appointment: models.Appointment, db: Session) -> bool:
    if appointment.stock_reserved is not None:
        return appointment.stock_reserved
    if appointment.status == models.AppointmentStatus.NEEDS_RESCHEDULE:
        response = (
            db.query(models.ResidentResponse)
            .filter(
                models.ResidentResponse.appointment_id == appointment.id,
                models.ResidentResponse.response_type == "reschedule_request",
            )
            .order_by(
                models.ResidentResponse.created_at.desc(),
                models.ResidentResponse.id.desc(),
            )
            .first()
        )
        if response:
            # Editing notes changed the old audit user too. Use resident history
            # and the explicit re-reservation ledger entry in that case.
            return (
                db.query(models.StockMovement.id)
                .filter(
                    models.StockMovement.note
                    == f"Opgave beholdt på planlagt dag, aftale {appointment.id}",
                    models.StockMovement.created_at > response.created_at,
                )
                .first()
                is not None
            )
    # Legacy planning deducted stock immediately. Resident rescheduling released
    # it and cleared the audit user; a VVS/admin meter issue kept the reservation.
    return not appointment.is_manual_task and (
        appointment.status
        in {
            models.AppointmentStatus.SCHEDULED,
            models.AppointmentStatus.INFORMED,
            models.AppointmentStatus.COMPLETED,
            models.AppointmentStatus.CLOSED,
            models.AppointmentStatus.NOT_HOME,
        }
        or (
            appointment.status == models.AppointmentStatus.NEEDS_RESCHEDULE
            and appointment.changed_by_user_id is not None
        )
    )


def complete_meter(
    db: Session, appointment: models.Appointment, user_id: int, changed_on: date
) -> None:
    if appointment.is_manual_task or appointment.address_id is None:
        raise ValueError("Vælg en adresse for at registrere målerskift")
    # Acquire SQLite's writer lock and reload before deciding whether to deduct.
    # A second request may have loaded this appointment before the first committed.
    db.flush()
    db.query(models.Appointment).filter(models.Appointment.id == appointment.id).update(
        {models.Appointment.stock_reserved: models.Appointment.stock_reserved},
        synchronize_session=False,
    )
    db.refresh(appointment)
    if not has_reserved_meter(appointment, db):
        stock = db.query(
            func.coalesce(func.sum(models.StockMovement.quantity), 0)
        ).scalar()
        if stock <= 0:
            raise ValueError(
                "Målerskift kan ikke registreres: der er ingen måler på lager"
            )
        db.add(
            models.StockMovement(
                movement_type=models.InventoryMovementType.RESERVE,
                quantity=-1,
                created_by_user_id=user_id,
                note=f"Målerskift, aftale {appointment.id}",
            )
        )
    appointment.stock_reserved = True
    appointment.status = models.AppointmentStatus.COMPLETED
    appointment.actual_changed_on = changed_on
    appointment.changed_date = utc_now()
    appointment.changed_by_user_id = user_id
    address = db.get(models.Address, appointment.address_id)
    address.blocked_reason = None
