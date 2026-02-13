from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
import re
import unicodedata

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/appointments", tags=["admin"])

UPLOAD_DIR = Path("data") / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PHOTO_LABELS = {
    "both": "Begge målere",
    "new": "Ny måler",
    "old": "Gammel måler",
}

PHOTO_FILENAME = {
    "both": "begge",
    "new": "ny",
    "old": "gammel",
}

STATUS_LABELS = {
    models.AppointmentStatus.SCHEDULED: "Planlagt",
    models.AppointmentStatus.INFORMED: "Beboer/kunde informeret",
    models.AppointmentStatus.COMPLETED: "Skiftet",
    models.AppointmentStatus.CLOSED: "Afsluttet",
    models.AppointmentStatus.NOT_HOME: "Ikke hjemme",
    models.AppointmentStatus.NEEDS_RESCHEDULE: "Behov for ny dato",
}


def appointment_photos(
    db: Session, appointment_ids: list[int]
) -> dict[int, list[models.AppointmentPhoto]]:
    photos = (
        db.query(models.AppointmentPhoto)
        .filter(models.AppointmentPhoto.appointment_id.in_(appointment_ids))
        .order_by(models.AppointmentPhoto.created_at.desc())
        .all()
    )
    grouped: dict[int, list[models.AppointmentPhoto]] = {}
    for photo in photos:
        grouped.setdefault(photo.appointment_id, []).append(photo)
    return grouped


def photo_complete(photos: list[models.AppointmentPhoto]) -> bool:
    types = {photo.photo_type for photo in photos}
    return "both" in types or ("new" in types and "old" in types)


def ensure_image(file: UploadFile) -> bool:
    return file.content_type is not None and file.content_type.startswith("image/")


def slugify_address(address: models.Address) -> str:
    value = f"{address.street}{address.house_no}".strip().lower()
    value = value.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", value) or "adresse"


def save_photo(address: models.Address, photo_type: str, file: UploadFile) -> str:
    extension = Path(file.filename or "").suffix.lower() or ".jpg"
    filename_slug = PHOTO_FILENAME.get(photo_type, "foto")
    slug = slugify_address(address)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    counter = 1

    folder = UPLOAD_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)

    while True:
        filename = f"{slug}-{filename_slug}-{timestamp}-{counter}{extension}"
        path = folder / filename
        if not path.exists():
            break
        counter += 1

    with path.open("wb") as buffer:
        buffer.write(file.file.read())
    return str(path.relative_to(UPLOAD_DIR))


def availability_dates(db: Session) -> list[date]:
    rows = (
        db.query(models.VvsAvailability.date)
        .distinct()
        .order_by(models.VvsAvailability.date)
        .all()
    )
    return [row[0] for row in rows]


def closest_date(dates: list[date]) -> date | None:
    if not dates:
        return None
    today = date.today()
    return min(dates, key=lambda day: (abs((day - today).days), 1 if day > today else 0))


def parse_time(raw: str) -> time:
    return datetime.strptime(raw, "%H:%M").time()


def duration_minutes_between(starts_at: datetime, ends_at: datetime) -> int:
    return int((ends_at - starts_at).total_seconds() // 60)


def availability_for_user(
    db: Session, user_id: int, plan_date: date
) -> models.VvsAvailability | None:
    return (
        db.query(models.VvsAvailability)
        .filter(
            models.VvsAvailability.user_id == user_id,
            models.VvsAvailability.date == plan_date,
        )
        .first()
    )


def available_vvs_for_date(db: Session, plan_date: date) -> list[models.User]:
    return (
        db.query(models.User)
        .join(models.VvsAvailability, models.VvsAvailability.user_id == models.User.id)
        .filter(
            models.User.role == models.UserRole.VVS,
            models.VvsAvailability.date == plan_date,
        )
        .order_by(models.User.username)
        .all()
    )


def has_conflict(
    db: Session,
    appointment_id: int,
    contractor_id: int,
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.id != appointment_id,
            models.Appointment.contractor_id == contractor_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.starts_at < ends_at,
            models.Appointment.ends_at > starts_at,
        )
        .first()
        is not None
    )


def has_conflict_for_user(
    db: Session,
    contractor_id: int,
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.contractor_id == contractor_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.starts_at < ends_at,
            models.Appointment.ends_at > starts_at,
        )
        .first()
        is not None
    )


@router.get("")
def appointment_overview(
    request: Request,
    date_query: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    dates = availability_dates(db)
    selected_date = None
    if date_query:
        try:
            selected_date = datetime.strptime(date_query, "%Y-%m-%d").date()
        except ValueError:
            flash(request, "Dato er ugyldig", "error")
            return RedirectResponse("/admin/appointments", status_code=303)
    elif dates:
        selected_date = closest_date(dates)

    if selected_date and selected_date not in dates:
        flash(request, "Vælg en arbejdsdag", "error")
        return RedirectResponse("/admin/appointments", status_code=303)

    rows = []
    if selected_date:
        rows = (
            db.query(models.Appointment, models.Address, models.User)
            .outerjoin(models.Address, models.Address.id == models.Appointment.address_id)
            .join(models.User, models.User.id == models.Appointment.contractor_id)
            .join(
                models.VvsAvailability,
                models.VvsAvailability.user_id == models.Appointment.contractor_id,
            )
            .filter(
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
                func.date(models.Appointment.starts_at) == models.VvsAvailability.date,
                func.date(models.Appointment.starts_at) == selected_date,
            )
            .order_by(models.Appointment.starts_at)
            .all()
        )

    appointments = [row[0] for row in rows]
    addresses = {row[0].id: row[1] for row in rows}
    contractors = {row[0].id: row[2] for row in rows}
    photos = appointment_photos(db, [appointment.id for appointment in appointments])
    vvs_users = available_vvs_for_date(db, selected_date) if selected_date else []
    todo = [
        appt
        for appt in appointments
        if appt.status in {models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.INFORMED}
    ]
    done = [
        appt
        for appt in appointments
        if appt.status not in {models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.INFORMED}
    ]

    return request.app.state.templates.TemplateResponse(
        "admin_appointments.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "appointments": appointments,
            "addresses": addresses,
            "contractors": contractors,
            "photos": photos,
            "todo": todo,
            "done": done,
            "availability_dates": dates,
            "selected_date": selected_date,
            "vvs_users": vvs_users,
            "photo_labels": PHOTO_LABELS,
            "status_labels": STATUS_LABELS,
        },
    )


@router.post("/manual-task")
def create_manual_task(
    request: Request,
    date_raw: str = Form(""),
    contractor_id: int = Form(0),
    start_raw: str = Form(""),
    duration_minutes: int = Form(30),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    if not date_raw:
        flash(request, "Vælg en dato", "error")
        return RedirectResponse("/admin/appointments", status_code=303)

    try:
        plan_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        start_time = parse_time(start_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    note_value = notes.strip()
    if not note_value:
        flash(request, "Skriv en opgave", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if contractor_id <= 0:
        flash(request, "Vælg VVS", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    contractor = db.query(models.User).filter(models.User.id == contractor_id).first()
    if not contractor or contractor.role != models.UserRole.VVS:
        flash(request, "Ugyldig VVS", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    availability = availability_for_user(db, contractor_id, plan_date)
    if not availability:
        flash(request, "VVS har ingen arbejdsdag på datoen", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if duration_minutes < 5 or duration_minutes > 480:
        flash(request, "Planlagt varighed skal være mellem 5 og 480 minutter", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    slot_start = datetime.combine(plan_date, start_time)
    slot_end = slot_start + timedelta(minutes=duration_minutes)
    window_start = time(8, 0)
    window_end = time(16, 0)

    if not (window_start <= start_time < window_end):
        flash(request, "Tid skal være mellem 08:00 og 16:00", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if slot_end.time() > window_end:
        flash(request, "Sluttid skal være senest 16:00", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if not (availability.start_time <= start_time < availability.end_time):
        flash(request, "Tid ligger udenfor arbejdsdag", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if slot_end.time() > availability.end_time:
        flash(request, "Slot slutter udenfor arbejdsdag", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    if has_conflict_for_user(db, contractor_id, slot_start, slot_end):
        flash(request, "VVS er allerede planlagt på dette tidspunkt", "error")
        return RedirectResponse(
            f"/admin/appointments?date_query={date_raw}", status_code=303
        )

    db.add(
        models.Appointment(
            address_id=None,
            contractor_id=contractor.id,
            starts_at=slot_start,
            ends_at=slot_end,
            status=models.AppointmentStatus.SCHEDULED,
            notes=note_value,
            changed_date=datetime.utcnow(),
            changed_by_user_id=user.id,
        )
    )
    db.commit()

    flash(request, "Opgave oprettet", "success")
    return RedirectResponse(
        f"/admin/appointments?date_query={plan_date.isoformat()}", status_code=303
    )


@router.post("/{appointment_id}/photos")
def upload_photo(
    request: Request,
    appointment_id: int,
    photo_type: str = Form(""),
    date_query: str | None = Form(None),
    redirect: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Opgave ikke fundet")

    redirect_target = "/admin/appointments"
    if redirect and redirect.startswith("/"):
        redirect_target = redirect
    elif date_query:
        redirect_target = f"/admin/appointments?date_query={date_query}"

    if appointment.address_id is None:
        flash(request, "Opgave uden adresse kan ikke få fotos", "error")
        return RedirectResponse(redirect_target, status_code=303)

    allowed_types = {"both", "new", "old"}
    if photo_type not in allowed_types:
        flash(request, "Vælg fototype", "error")
        return RedirectResponse(redirect_target, status_code=303)

    existing_photos = (
        db.query(models.AppointmentPhoto)
        .filter(models.AppointmentPhoto.appointment_id == appointment_id)
        .all()
    )
    existing_count = len(existing_photos)
    if existing_count >= 2:
        flash(request, "Der må kun uploades 2 billeder", "error")
        return RedirectResponse(redirect_target, status_code=303)

    if photo_type == "both" and existing_count > 0:
        flash(request, "Der findes allerede fotos for opgaven", "error")
        return RedirectResponse(redirect_target, status_code=303)

    if photo_type in {"new", "old"}:
        existing_types = {photo.photo_type for photo in existing_photos}
        if "both" in existing_types:
            flash(request, "Der findes allerede foto af begge målere", "error")
            return RedirectResponse(redirect_target, status_code=303)
        if photo_type in existing_types:
            flash(request, "Foto af denne type er allerede uploadet", "error")
            return RedirectResponse(redirect_target, status_code=303)

    if not ensure_image(file):
        flash(request, "Kun billedfiler er tilladt", "error")
        return RedirectResponse(redirect_target, status_code=303)

    address = db.query(models.Address).filter(models.Address.id == appointment.address_id).first()
    if not address:
        flash(request, "Adresse ikke fundet", "error")
        return RedirectResponse(redirect_target, status_code=303)

    file_path = save_photo(address, photo_type, file)
    photo = models.AppointmentPhoto(
        appointment_id=appointment.id,
        address_id=appointment.address_id,
        file_path=file_path,
        photo_type=photo_type,
        uploaded_by_user_id=user.id,
    )
    db.add(photo)
    db.commit()

    updated_photos = existing_photos + [photo]
    if photo_complete(updated_photos):
        appointment.status = models.AppointmentStatus.COMPLETED
        appointment.changed_date = datetime.utcnow()
        appointment.changed_by_user_id = user.id
        db.commit()
        flash(request, "Foto uploadet og status sat til skiftet", "success")
    else:
        flash(request, "Foto uploadet", "success")

    return RedirectResponse(redirect_target, status_code=303)


def appointment_edit_context(
    db: Session, appointment_id: int
) -> dict[str, object] | None:
    row = (
        db.query(models.Appointment, models.Address, models.User)
        .outerjoin(models.Address, models.Address.id == models.Appointment.address_id)
        .join(models.User, models.User.id == models.Appointment.contractor_id)
        .filter(models.Appointment.id == appointment_id)
        .first()
    )
    if not row:
        return None
    appointment, address, contractor = row
    availability = availability_for_user(db, contractor.id, appointment.starts_at.date())
    vvs_users = available_vvs_for_date(db, appointment.starts_at.date())
    if contractor not in vvs_users:
        vvs_users = [contractor] + vvs_users
    return {
        "appointment": appointment,
        "address": address,
        "contractor": contractor,
        "availability": availability,
        "vvs_users": vvs_users,
        "duration_minutes": duration_minutes_between(appointment.starts_at, appointment.ends_at),
    }


@router.get("/{appointment_id}/edit")
def edit_appointment(
    request: Request,
    appointment_id: int,
    inline: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    context = appointment_edit_context(db, appointment_id)
    if not context:
        raise HTTPException(status_code=404, detail="Opgave ikke fundet")

    template_name = (
        "partials/admin_appointment_form.html" if inline else "admin_appointment_edit.html"
    )
    base_context = {
        "request": request,
        "current_user": user,
        "appointment": context["appointment"],
        "address": context["address"],
        "contractor": context["contractor"],
        "availability": context["availability"],
        "vvs_users": context["vvs_users"],
        "duration_minutes": context["duration_minutes"],
        "inline": bool(inline),
        "errors": [],
    }
    if not inline:
        base_context["flashes"] = consume_flashes(request)

    return request.app.state.templates.TemplateResponse(
        template_name,
        base_context,
    )


@router.post("/{appointment_id}/edit")
def update_appointment(
    request: Request,
    appointment_id: int,
    status: str = Form(""),
    start_raw: str = Form(""),
    end_raw: str = Form(""),
    duration_minutes: int = Form(0),
    contractor_id: int = Form(0),
    old_meter_no: str = Form(""),
    new_meter_no: str = Form(""),
    notes: str = Form(""),
    inline: bool = Form(False),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Opgave ikke fundet")

    def inline_error(messages: list[str]):
        if not inline:
            return None
        context = appointment_edit_context(db, appointment_id)
        if not context:
            raise HTTPException(status_code=404, detail="Opgave ikke fundet")
        return request.app.state.templates.TemplateResponse(
            "partials/admin_appointment_form.html",
            {
                "request": request,
                "appointment": context["appointment"],
                "address": context["address"],
                "contractor": context["contractor"],
                "availability": context["availability"],
                "vvs_users": context["vvs_users"],
                "duration_minutes": context["duration_minutes"],
                "inline": True,
                "errors": messages,
            },
            status_code=400,
        )

    def handle_error(message: str):
        if inline:
            return inline_error([message])
        flash(request, message, "error")
        return RedirectResponse(f"/admin/appointments/{appointment_id}/edit", status_code=303)

    status_map = {
        "scheduled": models.AppointmentStatus.SCHEDULED,
        "informed": models.AppointmentStatus.INFORMED,
        "completed": models.AppointmentStatus.COMPLETED,
        "closed": models.AppointmentStatus.CLOSED,
        "not_home": models.AppointmentStatus.NOT_HOME,
        "needs_reschedule": models.AppointmentStatus.NEEDS_RESCHEDULE,
    }
    if status not in status_map:
        return handle_error("Vælg en gyldig status")

    contractor = db.query(models.User).filter(models.User.id == contractor_id).first()
    if not contractor or contractor.role != models.UserRole.VVS:
        return handle_error("Ugyldig VVS")

    try:
        start_time = parse_time(start_raw)
    except ValueError:
        return handle_error("Tid er ugyldig")

    end_time = None
    if end_raw:
        try:
            end_time = parse_time(end_raw)
        except ValueError:
            return handle_error("Tid er ugyldig")

    if end_time is None and duration_minutes <= 0:
        return handle_error("Angiv sluttid eller planlagt varighed")

    plan_date = appointment.starts_at.date()
    starts_at = datetime.combine(plan_date, start_time)
    if end_time is None:
        ends_at = starts_at + timedelta(minutes=duration_minutes)
    else:
        ends_at = datetime.combine(plan_date, end_time)

    if ends_at <= starts_at:
        return handle_error("Sluttid skal være efter start")

    calculated_minutes = duration_minutes_between(starts_at, ends_at)
    if duration_minutes > 0 and calculated_minutes != duration_minutes:
        return handle_error("Sluttid matcher ikke planlagt varighed")

    if calculated_minutes < 5 or calculated_minutes > 480:
        return handle_error("Planlagt varighed skal være mellem 5 og 480 minutter")

    if not (time(8, 0) <= start_time < time(16, 0)):
        return handle_error("Tid skal være mellem 08:00 og 16:00")

    if ends_at.time() > time(16, 0):
        return handle_error("Sluttid skal være senest 16:00")

    availability = availability_for_user(db, contractor.id, plan_date)
    if status_map[status] == models.AppointmentStatus.SCHEDULED:
        if not availability:
            return handle_error("Ingen arbejdsdag registreret på dagen")
        if not (availability.start_time <= start_time < availability.end_time):
            return handle_error("Tid ligger udenfor arbejdsdag")
        if ends_at.time() > availability.end_time:
            return handle_error("Slot slutter udenfor arbejdsdag")
        if has_conflict(db, appointment.id, contractor.id, starts_at, ends_at):
            return handle_error("VVS er allerede planlagt på dette tidspunkt")

    appointment.status = status_map[status]
    appointment.contractor_id = contractor.id
    appointment.starts_at = starts_at
    appointment.ends_at = ends_at
    appointment.old_meter_no = old_meter_no.strip() or None
    appointment.new_meter_no = new_meter_no.strip() or None
    appointment.notes = notes.strip() or None
    appointment.changed_date = datetime.utcnow()
    appointment.changed_by_user_id = user.id
    db.commit()

    if inline:
        return JSONResponse({"success": True})

    flash(request, "Opgave opdateret", "success")
    return RedirectResponse("/admin/appointments", status_code=303)


@router.post("/{appointment_id}/close")
def close_appointment(
    request: Request,
    appointment_id: int,
    date_query: str | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Opgave ikke fundet")

    appointment.status = models.AppointmentStatus.CLOSED
    appointment.changed_date = datetime.utcnow()
    appointment.changed_by_user_id = user.id
    db.commit()

    redirect_target = "/admin/appointments"
    if date_query:
        redirect_target = f"/admin/appointments?date_query={date_query}"

    flash(request, "Opgave afsluttet", "success")
    return RedirectResponse(redirect_target, status_code=303)
