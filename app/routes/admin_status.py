from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role

router = APIRouter(prefix="/admin/status", tags=["admin"])

COMPLETED_STATUSES = {models.AppointmentStatus.COMPLETED}
INFORMED_STATUSES = {models.AppointmentStatus.INFORMED}
CLOSED_STATUSES = {models.AppointmentStatus.CLOSED}
PLANNED_STATUSES = {models.AppointmentStatus.SCHEDULED}


def latest_status_map(
    db: Session, address_ids: list[int]
) -> dict[int, models.AppointmentStatus]:
    if not address_ids:
        return {}

    appointments = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id.in_(address_ids),
            models.Appointment.status.in_([
                *COMPLETED_STATUSES,
                *CLOSED_STATUSES,
                *INFORMED_STATUSES,
                *PLANNED_STATUSES,
                models.AppointmentStatus.NOT_HOME,
                models.AppointmentStatus.NEEDS_RESCHEDULE,
            ]),
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )

    status_map: dict[int, models.AppointmentStatus] = {}
    for appointment in appointments:
        if appointment.address_id in status_map:
            continue
        status_map[appointment.address_id] = appointment.status
    return status_map


@router.get("")
def status_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    addresses = db.query(models.Address).order_by(models.Address.street).all()
    address_ids = [address.id for address in addresses]
    status_map = latest_status_map(db, address_ids)

    completed_ids = {aid for aid, status in status_map.items() if status in COMPLETED_STATUSES}
    closed_ids = {aid for aid, status in status_map.items() if status in CLOSED_STATUSES}
    informed_ids = {aid for aid, status in status_map.items() if status in INFORMED_STATUSES}
    planned_ids = {aid for aid, status in status_map.items() if status in PLANNED_STATUSES}
    not_home_ids = {
        aid
        for aid, status in status_map.items()
        if status == models.AppointmentStatus.NOT_HOME
    }
    not_home_total = (
        db.query(func.count(models.Appointment.id))
        .filter(models.Appointment.status == models.AppointmentStatus.NOT_HOME)
        .scalar()
        or 0
    )
    needs_reschedule_ids = {
        aid
        for aid, status in status_map.items()
        if status == models.AppointmentStatus.NEEDS_RESCHEDULE
    }

    total = len(addresses)
    completed = len(completed_ids)
    closed = len(closed_ids)
    informed = len(informed_ids)
    planned = len(planned_ids)
    not_home = len(not_home_ids)
    needs_reschedule = len(needs_reschedule_ids)
    remaining = max(
        total - completed - closed - informed - planned - not_home - needs_reschedule, 0
    )
    not_home_count = not_home_total
    stock = db.query(func.coalesce(func.sum(models.StockMovement.quantity), 0)).scalar() or 0

    street_totals: dict[str, int] = defaultdict(int)
    street_completed: dict[str, int] = defaultdict(int)

    for address in addresses:
        street_totals[address.street] += 1
        if address.id in completed_ids:
            street_completed[address.street] += 1

    street_progress = []
    for street, total_count in street_totals.items():
        done = street_completed.get(street, 0)
        street_progress.append(
            {
                "street": street,
                "completed": done,
                "total": total_count,
                "is_complete": done == total_count,
            }
        )

    street_progress.sort(key=lambda row: row["street"].lower())

    availability_dates = [
        row[0]
        for row in db.query(models.VvsAvailability.date)
        .distinct()
        .order_by(models.VvsAvailability.date.desc())
        .all()
    ]
    day_status = []
    for day in availability_dates:
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)
        total_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
            )
            .scalar()
            or 0
        )
        completed_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status.in_(COMPLETED_STATUSES),
            )
            .scalar()
            or 0
        )
        closed_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status.in_(CLOSED_STATUSES),
            )
            .scalar()
            or 0
        )
        informed_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status.in_(INFORMED_STATUSES),
            )
            .scalar()
            or 0
        )
        not_home_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status == models.AppointmentStatus.NOT_HOME,
            )
            .scalar()
            or 0
        )
        day_status.append(
            {
                "date": day,
                "completed": completed_count,
                "closed": closed_count,
                "informed": informed_count,
                "not_home": not_home_count,
                "total": total_count,
            }
        )

    return request.app.state.templates.TemplateResponse(
        "admin_status.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "total": total,
            "completed": completed,
            "closed": closed,
            "informed": informed,
            "planned": planned,
            "not_home": not_home_count,
            "needs_reschedule": needs_reschedule,
            "remaining": remaining,
            "stock": stock,
            "street_progress": street_progress,
            "day_status": day_status,
        },
    )
