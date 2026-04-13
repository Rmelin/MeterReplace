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


def relative_day_label(day_offset: int) -> str:
    if day_offset == 0:
        return "I dag"
    if day_offset == 1:
        return "Om 1 dag"
    if day_offset > 1:
        return f"Om {day_offset} dage"
    if day_offset == -1:
        return "1 dag siden"
    return f"{abs(day_offset)} dage siden"


def latest_status_map(
    db: Session, address_ids: list[int]
) -> dict[int, models.AppointmentStatus]:
    if not address_ids:
        return {}

    appointments = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id.in_(address_ids),
            models.Appointment.status.in_(
                [
                    *COMPLETED_STATUSES,
                    *CLOSED_STATUSES,
                    *INFORMED_STATUSES,
                    *PLANNED_STATUSES,
                    models.AppointmentStatus.NOT_HOME,
                    models.AppointmentStatus.NEEDS_RESCHEDULE,
                    models.AppointmentStatus.NOT_SCHEDULED,
                ]
            ),
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )

    status_map: dict[int, models.AppointmentStatus] = {}
    notscheduled_map: dict[int, models.AppointmentStatus] = {}
    for appointment in appointments:
        if appointment.status == models.AppointmentStatus.NOT_SCHEDULED:
            if appointment.address_id not in notscheduled_map:
                notscheduled_map[appointment.address_id] = appointment.status
            continue
        if appointment.address_id in status_map:
            continue
        status_map[appointment.address_id] = appointment.status
    for address_id, status in notscheduled_map.items():
        if address_id not in status_map:
            status_map[address_id] = status
    register_closed_ids = {
        row[0]
        for row in db.query(models.Address.id)
        .filter(
            models.Address.id.in_(address_ids),
            models.Address.register_closed.is_(True),
        )
        .all()
    }
    for address_id in register_closed_ids:
        status_map[address_id] = models.AppointmentStatus.CLOSED
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
    pre_total = planned + informed
    post_total = completed + closed
    remaining = max(
        total - completed - closed - informed - planned - not_home - needs_reschedule, 0
    )
    not_home_history_count = not_home_total
    stock = db.query(func.coalesce(func.sum(models.StockMovement.quantity), 0)).scalar() or 0
    message_count = (
        db.query(func.count(func.distinct(models.ResidentResponse.address_id)))
        .filter(models.ResidentResponse.message.is_not(None))
        .filter(models.ResidentResponse.message != "")
        .scalar()
        or 0
    )

    street_totals: dict[str, int] = defaultdict(int)
    street_completed: dict[str, int] = defaultdict(int)

    done_ids = completed_ids | closed_ids
    for address in addresses:
        street_totals[address.street] += 1
        if address.id in done_ids:
            street_completed[address.street] += 1

    street_progress = []
    for street, total_count in street_totals.items():
        done = street_completed.get(street, 0)
        remaining_count = max(total_count - done, 0)
        completion_pct = round((done / total_count) * 100) if total_count else 0
        street_progress.append(
            {
                "street": street,
                "completed": done,
                "total": total_count,
                "remaining": remaining_count,
                "completion_pct": completion_pct,
                "is_complete": done == total_count,
                "state_key": "done" if done == total_count else "active",
                "state_label": "Færdig" if done == total_count else "I gang",
            }
        )

    street_progress.sort(
        key=lambda row: (
            row["is_complete"],
            -row["remaining"],
            row["street"].lower(),
        )
    )
    active_street_progress = [row for row in street_progress if not row["is_complete"]]
    completed_street_progress = [row for row in street_progress if row["is_complete"]]

    availability_dates = [
        row[0]
        for row in db.query(models.VvsAvailability.date)
        .distinct()
        .order_by(models.VvsAvailability.date.desc())
        .all()
    ]
    today = datetime.now().date()
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
        planned_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status.in_(PLANNED_STATUSES),
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
        day_not_home_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status == models.AppointmentStatus.NOT_HOME,
            )
            .scalar()
            or 0
        )
        done_count = completed_count + closed_count
        remaining_count = max(total_count - done_count, 0)
        completion_pct = round((done_count / total_count) * 100) if total_count else 0
        day_offset = (day - today).days
        if day_offset > 0:
            state_key = "upcoming"
            state_label = "Kommende"
        elif day_offset == 0:
            state_key = "today"
            state_label = "I dag"
        elif remaining_count == 0 and total_count > 0:
            state_key = "done"
            state_label = "Færdig"
        else:
            state_key = "history"
            state_label = "Historik"
        day_status.append(
            {
                "date": day,
                "planned": planned_count,
                "completed": completed_count,
                "closed": closed_count,
                "informed": informed_count,
                "not_home": day_not_home_count,
                "done": done_count,
                "remaining": remaining_count,
                "completion_pct": completion_pct,
                "day_offset": day_offset,
                "relative_label": relative_day_label(day_offset),
                "state_key": state_key,
                "state_label": state_label,
                "total": total_count,
            }
        )

    today_day_status = [row for row in day_status if row["day_offset"] == 0]
    upcoming_day_status = sorted(
        [row for row in day_status if row["day_offset"] > 0],
        key=lambda row: row["date"],
    )
    recent_day_status = sorted(
        [row for row in day_status if -7 <= row["day_offset"] < 0],
        key=lambda row: row["date"],
        reverse=True,
    )
    older_day_status = sorted(
        [row for row in day_status if row["day_offset"] < -7],
        key=lambda row: row["date"],
        reverse=True,
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
            "pre_total": pre_total,
            "post_total": post_total,
            "not_home": not_home_history_count,
            "needs_reschedule": needs_reschedule,
            "remaining": remaining,
            "stock": stock,
            "message_count": message_count,
            "active_street_progress": active_street_progress,
            "completed_street_progress": completed_street_progress,
            "today_day_status": today_day_status,
            "upcoming_day_status": upcoming_day_status,
            "recent_day_status": recent_day_status,
            "older_day_status": older_day_status,
        },
    )
