from datetime import datetime, time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/dashboard")
def user_dashboard(
    request: Request,
    date_query: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.USER)),
):
    availability_dates = [
        row[0]
        for row in db.query(models.VvsAvailability.date)
        .distinct()
        .order_by(models.VvsAvailability.date.desc())
        .all()
    ]
    selected_date = None
    if date_query:
        try:
            selected_date = datetime.strptime(date_query, "%Y-%m-%d").date()
        except ValueError:
            selected_date = None
    elif availability_dates:
        selected_date = availability_dates[0]

    scheduled_addresses = []
    if selected_date:
        day_start = datetime.combine(selected_date, time.min)
        day_end = datetime.combine(selected_date, time.max)
        scheduled_addresses = (
            db.query(models.Address)
            .join(models.Appointment, models.Appointment.address_id == models.Address.id)
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at <= day_end,
                models.Appointment.status.in_(
                    [
                        models.AppointmentStatus.SCHEDULED,
                        models.AppointmentStatus.INFORMED,
                        models.AppointmentStatus.COMPLETED,
                        models.AppointmentStatus.CLOSED,
                        models.AppointmentStatus.NOT_HOME,
                        models.AppointmentStatus.NEEDS_RESCHEDULE,
                    ]
                ),
            )
            .order_by(models.Appointment.starts_at)
            .all()
        )

    return request.app.state.templates.TemplateResponse(
        "user_dashboard.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "availability_dates": availability_dates,
            "selected_date": selected_date,
            "scheduled_addresses": scheduled_addresses,
        },
    )
