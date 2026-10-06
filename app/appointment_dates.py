from sqlalchemy import case, func

from app import models


def work_date():
    """Use the actual replacement date for finished meter visits, the plan otherwise."""
    return case(
        (
            models.Appointment.is_manual_task.is_(False)
            & models.Appointment.status.in_(
                [
                    models.AppointmentStatus.COMPLETED,
                    models.AppointmentStatus.CLOSED,
                ]
            ),
            func.coalesce(
                models.Appointment.actual_changed_on,
                func.date(models.Appointment.starts_at),
            ),
        ),
        else_=func.date(models.Appointment.starts_at),
    )
