from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.planning_slots import availability_slots, build_slots

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


def build_workday_status(db: Session) -> dict[str, object]:
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
        slot_total = len(availability_slots(db, day))
        free_slot_count = len(build_slots(db, day))
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
        needs_reschedule_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at < day_end,
                models.Appointment.status == models.AppointmentStatus.NEEDS_RESCHEDULE,
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
        booked_count = planned_count + informed_count
        day_offset = (day - today).days
        display_total = slot_total if day_offset > 0 else total_count
        display_free_slots = max(slot_total - booked_count, 0) if day_offset > 0 else free_slot_count
        booking_pct = round((booked_count / slot_total) * 100) if slot_total else 0
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
                "needs_reschedule": needs_reschedule_count,
                "not_home": day_not_home_count,
                "done": done_count,
                "remaining": remaining_count,
                "completion_pct": completion_pct,
                "booking_pct": booking_pct,
                "booked": booked_count,
                "slot_total": slot_total,
                "free_slots": free_slot_count,
                "display_total": display_total,
                "display_free_slots": display_free_slots,
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
    available_workday_slots = sum(
        row["display_free_slots"] if row["day_offset"] > 0 else row["free_slots"]
        for row in day_status
        if row["day_offset"] >= 0
    )
    active_planned_workday_status = [
        row
        for row in day_status
        if row["day_offset"] >= 0
        and row["planned"] + row["informed"] + row["needs_reschedule"] > 0
    ]
    open_slots_on_active_planned_workdays = sum(
        row["display_free_slots"] if row["day_offset"] > 0 else row["free_slots"]
        for row in active_planned_workday_status
    )
    reschedule_on_active_planned_workdays = sum(
        row["needs_reschedule"] for row in active_planned_workday_status
    )

    return {
        "day_status": day_status,
        "today_day_status": today_day_status,
        "upcoming_day_status": upcoming_day_status,
        "recent_day_status": recent_day_status,
        "older_day_status": older_day_status,
        "available_workday_slots": available_workday_slots,
        "open_slots_on_active_planned_workdays": open_slots_on_active_planned_workdays,
        "reschedule_on_active_planned_workdays": reschedule_on_active_planned_workdays,
    }
