from __future__ import annotations

from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role
from app.workday_status import build_workday_status

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
    status_line_missing = max(total - planned - informed - completed - closed, 0)
    status_line_segments = [
        {
            "key": "missing",
            "label": "Mangler",
            "count": status_line_missing,
            "pct": round((status_line_missing / total) * 100) if total else 0,
            "style": "missing",
        },
        {
            "key": "planned",
            "label": "Planlagt",
            "count": planned,
            "pct": round((planned / total) * 100) if total else 0,
            "style": "planned",
        },
        {
            "key": "informed",
            "label": "Informeret",
            "count": informed,
            "pct": round((informed / total) * 100) if total else 0,
            "style": "informed",
        },
        {
            "key": "completed",
            "label": "Skiftet",
            "count": completed,
            "pct": round((completed / total) * 100) if total else 0,
            "style": "completed",
        },
        {
            "key": "closed",
            "label": "Afsluttet",
            "count": closed,
            "pct": round((closed / total) * 100) if total else 0,
            "style": "closed",
        },
    ]
    stock_coverable_missing = min(stock, remaining)
    meters_missing_after_stock = max(remaining - stock, 0)
    stock_coverage_pct = (
        round((stock_coverable_missing / remaining) * 100)
        if remaining
        else 100
    )
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

    workday_status = build_workday_status(db)

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
            "status_line_segments": status_line_segments,
            "status_line_missing": status_line_missing,
            "stock": stock,
            "stock_coverable_missing": stock_coverable_missing,
            "meters_missing_after_stock": meters_missing_after_stock,
            "stock_coverage_pct": stock_coverage_pct,
            "message_count": message_count,
            "available_workday_slots": workday_status["available_workday_slots"],
            "open_slots_on_active_planned_workdays": workday_status[
                "open_slots_on_active_planned_workdays"
            ],
            "reschedule_on_active_planned_workdays": workday_status[
                "reschedule_on_active_planned_workdays"
            ],
            "active_street_progress": active_street_progress,
            "completed_street_progress": completed_street_progress,
            "today_day_status": workday_status["today_day_status"],
            "upcoming_day_status": workday_status["upcoming_day_status"],
            "recent_day_status": workday_status["recent_day_status"],
            "older_day_status": workday_status["older_day_status"],
        },
    )
