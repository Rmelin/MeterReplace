from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app import models

SLOT_OCCUPYING_STATUSES = {
    models.AppointmentStatus.SCHEDULED,
    models.AppointmentStatus.INFORMED,
    models.AppointmentStatus.COMPLETED,
    models.AppointmentStatus.CLOSED,
    models.AppointmentStatus.NOT_HOME,
}


def availability_slots(
    db: Session, plan_date: date
) -> list[tuple[models.User, datetime, datetime]]:
    availability = (
        db.query(models.VvsAvailability, models.User)
        .join(models.User, models.User.id == models.VvsAvailability.user_id)
        .filter(models.VvsAvailability.date == plan_date)
        .order_by(models.User.username)
        .all()
    )
    slots: list[tuple[models.User, datetime, datetime]] = []
    windows = [(time(8, 0), time(12, 0)), (time(12, 0), time(16, 0))]

    for entry, contractor in availability:
        for window_start, window_end in windows:
            start = max(entry.start_time, window_start)
            end = min(entry.end_time, window_end)
            if start >= end:
                continue
            current = datetime.combine(plan_date, start)
            end_dt = datetime.combine(plan_date, end)
            while current + timedelta(minutes=30) <= end_dt:
                slots.append((contractor, current, current + timedelta(minutes=30)))
                current += timedelta(minutes=30)

    slots.sort(key=lambda item: (item[1], item[0].username))
    return slots


def occupied_slots_by_contractor(
    db: Session, plan_date: date
) -> dict[int, list[tuple[datetime, datetime]]]:
    day_start = datetime.combine(plan_date, time.min)
    day_end = datetime.combine(plan_date, time.max)
    appointments = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.status.in_(SLOT_OCCUPYING_STATUSES),
            models.Appointment.starts_at <= day_end,
            models.Appointment.ends_at >= day_start,
        )
        .all()
    )
    occupied: dict[int, list[tuple[datetime, datetime]]] = {}
    for appointment in appointments:
        occupied.setdefault(appointment.contractor_id, []).append(
            (appointment.starts_at, appointment.ends_at)
        )
    return occupied


def build_slots(db: Session, plan_date: date) -> list[tuple[models.User, datetime, datetime]]:
    occupied = occupied_slots_by_contractor(db, plan_date)
    slots = []
    for contractor, starts_at, ends_at in availability_slots(db, plan_date):
        overlaps_existing = any(
            existing_start < ends_at and existing_end > starts_at
            for existing_start, existing_end in occupied.get(contractor.id, [])
        )
        if overlaps_existing:
            continue
        slots.append((contractor, starts_at, ends_at))
    return slots
