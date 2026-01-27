from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/vvs", tags=["vvs"])


def parse_date(date_raw: str):
    return datetime.strptime(date_raw, "%Y-%m-%d").date()


def parse_time(time_raw: str):
    return datetime.strptime(time_raw, "%H:%M").time()


def validate_time_window(start: time, end: time) -> bool:
    window_start = time(6, 0)
    window_end = time(18, 0)
    return start < end and window_start <= start <= window_end and window_start <= end <= window_end


def has_scheduled_appointments(db: Session, user_id: int, entry_date) -> bool:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.contractor_id == user_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            func.date(models.Appointment.starts_at) == entry_date,
        )
        .first()
        is not None
    )


@router.get("")
def vvs_availability(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.VVS)),
):
    entries = (
        db.query(models.VvsAvailability)
        .filter(models.VvsAvailability.user_id == user.id)
        .order_by(models.VvsAvailability.date.desc())
        .limit(30)
        .all()
    )
    return request.app.state.templates.TemplateResponse(
        "vvs_availability.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "entries": entries,
        },
    )


@router.post("")
def create_availability(
    request: Request,
    date_raw: str = Form(""),
    start_raw: str = Form(""),
    end_raw: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.VVS)),
):
    note = note.strip() or None
    try:
        entry_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
        end_time = parse_time(end_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse("/vvs", status_code=303)

    if not validate_time_window(start_time, end_time):
        flash(request, "Tid skal være mellem 06:00 og 18:00", "error")
        return RedirectResponse("/vvs", status_code=303)

    entry = models.VvsAvailability(
        user_id=user.id,
        date=entry_date,
        start_time=start_time,
        end_time=end_time,
        note=note,
    )
    db.add(entry)
    db.commit()
    flash(request, "Arbejdsdag gemt", "success")
    return RedirectResponse("/vvs", status_code=303)


@router.get("/{availability_id}/edit")
def edit_availability_form(
    request: Request,
    availability_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.VVS)),
):
    entry = (
        db.query(models.VvsAvailability)
        .filter(
            models.VvsAvailability.id == availability_id,
            models.VvsAvailability.user_id == user.id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Arbejdsdag ikke fundet")


    note = note.strip() or None
    try:
        entry_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
        end_time = parse_time(end_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse(f"/vvs/{availability_id}/edit", status_code=303)

    if not validate_time_window(start_time, end_time):
        flash(request, "Tid skal være mellem 06:00 og 18:00", "error")
        return RedirectResponse(f"/vvs/{availability_id}/edit", status_code=303)

    entry.date = entry_date
    entry.start_time = start_time
    entry.end_time = end_time
    entry.note = note
    db.commit()

    if has_scheduled_appointments(db, user.id, entry_date):
        flash(
            request,
            "Advarsel: Der er allerede planlagte opgaver på denne dato.",
            "error",
        )
    else:
        flash(request, "Arbejdsdag opdateret", "success")

    return RedirectResponse("/vvs", status_code=303)
