from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/availability", tags=["admin"])


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
def availability_overview(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    vvs_users = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.VVS)
        .order_by(models.User.username)
        .all()
    )
    rows = (
        db.query(models.VvsAvailability, models.User)
        .join(models.User, models.User.id == models.VvsAvailability.user_id)
        .order_by(models.VvsAvailability.date.desc())
        .limit(50)
        .all()
    )
    entries = [
        {"entry": entry, "username": vvs_user.username} for entry, vvs_user in rows
    ]
    return request.app.state.templates.TemplateResponse(
        "admin_availability.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "vvs_users": vvs_users,
            "entries": entries,
        },
    )


@router.post("")
def create_availability(
    request: Request,
    user_id: int = Form(0),
    date_raw: str = Form(""),
    start_raw: str = Form(""),
    end_raw: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    note = note.strip() or None
    if user_id <= 0:
        flash(request, "Vælg en VVS", "error")
        return RedirectResponse("/admin/availability", status_code=303)

    vvs_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not vvs_user or vvs_user.role != models.UserRole.VVS:
        flash(request, "Ugyldig VVS", "error")
        return RedirectResponse("/admin/availability", status_code=303)

    try:
        entry_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
        end_time = parse_time(end_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse("/admin/availability", status_code=303)

    if not validate_time_window(start_time, end_time):
        flash(request, "Tid skal være mellem 06:00 og 18:00", "error")
        return RedirectResponse("/admin/availability", status_code=303)

    entry = models.VvsAvailability(
        user_id=vvs_user.id,
        date=entry_date,
        start_time=start_time,
        end_time=end_time,
        note=note,
    )
    db.add(entry)
    db.commit()

    flash(request, "Arbejdsdag gemt", "success")
    return RedirectResponse("/admin/availability", status_code=303)


@router.get("/{availability_id}/edit")
def edit_availability_form(
    request: Request,
    availability_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    entry = (
        db.query(models.VvsAvailability, models.User)
        .join(models.User, models.User.id == models.VvsAvailability.user_id)
        .filter(models.VvsAvailability.id == availability_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Arbejdsdag ikke fundet")

    availability, vvs_user = entry
    has_conflict = has_scheduled_appointments(db, vvs_user.id, availability.date)

    return request.app.state.templates.TemplateResponse(
        "admin_availability_edit.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "entry": availability,
            "vvs_user": vvs_user,
            "has_conflict": has_conflict,
        },
    )


@router.post("/{availability_id}/edit")
def update_availability(
    request: Request,
    availability_id: int,
    date_raw: str = Form(""),
    start_raw: str = Form(""),
    end_raw: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    entry = db.query(models.VvsAvailability).filter(
        models.VvsAvailability.id == availability_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Arbejdsdag ikke fundet")

    note = note.strip() or None
    try:
        entry_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
        end_time = parse_time(end_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse(
            f"/admin/availability/{availability_id}/edit", status_code=303
        )

    if not validate_time_window(start_time, end_time):
        flash(request, "Tid skal være mellem 06:00 og 18:00", "error")
        return RedirectResponse(
            f"/admin/availability/{availability_id}/edit", status_code=303
        )

    entry.date = entry_date
    entry.start_time = start_time
    entry.end_time = end_time
    entry.note = note
    db.commit()

    if has_scheduled_appointments(db, entry.user_id, entry_date):
        flash(
            request,
            "Advarsel: Der er allerede planlagte opgaver på denne dato.",
            "error",
        )
    else:
        flash(request, "Arbejdsdag opdateret", "success")

    return RedirectResponse("/admin/availability", status_code=303)
