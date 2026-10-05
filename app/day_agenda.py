from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models


STATUS_LABELS = {
    models.AppointmentStatus.SCHEDULED: "Planlagt",
    models.AppointmentStatus.INFORMED: "Beboer/kunde informeret",
    models.AppointmentStatus.COMPLETED: "Skiftet",
    models.AppointmentStatus.CLOSED: "Afsluttet",
    models.AppointmentStatus.NOT_HOME: "Ikke hjemme",
    models.AppointmentStatus.NEEDS_RESCHEDULE: "Behov for ny dato",
}


def agenda_group(window: str, starts_at: datetime, is_meter_pit: bool) -> str:
    if window == "all_day" or is_meter_pit:
        return "all_day"
    if window in {"morning", "afternoon"}:
        return window
    return "morning" if starts_at.time() < time(12) else "afternoon"


def day_agenda(db: Session, day: date, drafts=()) -> list[dict]:
    start = datetime.combine(day, time.min)
    rows = (
        db.query(models.Appointment, models.Address, models.User)
        .outerjoin(models.Address, models.Address.id == func.coalesce(models.Appointment.task_address_id, models.Appointment.address_id))
        .join(models.User, models.User.id == models.Appointment.contractor_id)
        .filter(
            or_(
                (models.Appointment.starts_at >= start)
                & (models.Appointment.starts_at < start + timedelta(days=1)),
                (models.Appointment.status == models.AppointmentStatus.COMPLETED)
                & (models.Appointment.actual_changed_on == day)
                & models.Appointment.is_manual_task.is_(False),
            ),
            models.Appointment.status.in_(list(STATUS_LABELS)),
        )
        .all()
    )
    agenda = []
    for appointment, address, contractor in rows:
        window = appointment.time_window if appointment.is_manual_task else "exact"
        period = {"all_day": "Hele dagen", "morning": "Formiddag", "afternoon": "Eftermiddag"}.get(window)
        agenda.append({
            "starts_at": appointment.starts_at,
            "all_day": window == "all_day",
            "time_label": period or f"{appointment.starts_at:%H:%M}–{appointment.ends_at:%H:%M}",
            "kind": "VVS-opgave" if appointment.is_manual_task else "Målerskift",
            "description": appointment.notes if appointment.is_manual_task else None,
            "note": appointment.notes,
            "changed_on": appointment.meter_changed_on if appointment.status == models.AppointmentStatus.COMPLETED and not appointment.is_manual_task else None,
            "planned_on": appointment.starts_at.date(),
            "buffer_note": address.buffer_note if address and address.buffer_flag and not appointment.is_manual_task else None,
            "group": agenda_group(window, appointment.starts_at, bool(address and address.buffer_flag and not appointment.is_manual_task)),
            "is_done": appointment.status in {models.AppointmentStatus.COMPLETED, models.AppointmentStatus.CLOSED, models.AppointmentStatus.NOT_HOME},
            "is_meter_issue": bool(not appointment.is_manual_task and address and address.blocked_reason == "Fejl ved måler" and appointment.status == models.AppointmentStatus.NEEDS_RESCHEDULE),
            "address": address,
            "contractor": contractor.username,
            "status": "Udført" if appointment.is_manual_task and appointment.status == models.AppointmentStatus.CLOSED else STATUS_LABELS[appointment.status],
            "is_draft": False,
            "href": f"/admin/appointments?date_query={day.isoformat()}#appointment-{appointment.id}",
        })
    for draft in drafts:
        agenda.append({
            "starts_at": draft.starts_at,
            "all_day": False,
            "time_label": f"{draft.starts_at:%H:%M}–{draft.ends_at:%H:%M}",
            "kind": "Målerskift",
            "description": None,
            "note": None,
            "buffer_note": draft.address.buffer_note if draft.is_buffer else None,
            "group": agenda_group("exact", draft.starts_at, draft.is_buffer),
            "is_done": False,
            "is_meter_issue": False,
            "address": draft.address,
            "contractor": draft.contractor.username,
            "status": "Udkast",
            "is_draft": True,
            "href": "#planning-draft",
        })
    return sorted(agenda, key=lambda item: (not item["all_day"], item["starts_at"], item["contractor"]))
