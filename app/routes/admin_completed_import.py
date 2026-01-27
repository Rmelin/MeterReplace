from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/import/completed", tags=["admin"])

UPLOAD_DIR = Path("data") / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"both", "new", "old"}
ALLOWED_STATUSES = {
    "draft",
    "scheduled",
    "informed",
    "completed",
    "closed",
    "not_home",
    "needs_reschedule",
}

STATUS_MAP = {
    "draft": models.AppointmentStatus.DRAFT,
    "scheduled": models.AppointmentStatus.SCHEDULED,
    "informed": models.AppointmentStatus.INFORMED,
    "completed": models.AppointmentStatus.COMPLETED,
    "closed": models.AppointmentStatus.CLOSED,
    "not_home": models.AppointmentStatus.NOT_HOME,
    "needs_reschedule": models.AppointmentStatus.NEEDS_RESCHEDULE,
}


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text) or "adresse"


def slugify_address(address: models.Address) -> str:
    return slugify(f"{address.street}{address.house_no}")


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def resolve_vvs(db: Session, vvs_name: str) -> models.User | None:
    return (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.VVS,
            models.User.username == vvs_name,
        )
        .first()
    )


def resolve_address(db: Session, street: str, house_no: str, zip_code: str, city: str) -> models.Address | None:
    return (
        db.query(models.Address)
        .filter(
            models.Address.street == street,
            models.Address.house_no == house_no,
            models.Address.zip == zip_code,
            models.Address.city == city,
        )
        .first()
    )


def save_zip_photo(address: models.Address, photo_type: str, filename: str, data: bytes) -> str:
    slug = slugify_address(address)
    extension = Path(filename).suffix.lower() or ".jpg"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    counter = 1
    folder = UPLOAD_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        target_name = f"{slug}-{photo_type}-{timestamp}-{counter}{extension}"
        path = folder / target_name
        if not path.exists():
            break
        counter += 1
    with path.open("wb") as buffer:
        buffer.write(data)
    return str(path.relative_to(UPLOAD_DIR))


def read_zip(zip_file: UploadFile | None) -> dict[str, bytes]:
    if not zip_file or not zip_file.filename:
        return {}
    data = zip_file.file.read()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def parse_photo_list(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def ensure_closed(appointment: models.Appointment, user: models.User) -> None:
    appointment.status = models.AppointmentStatus.CLOSED
    appointment.changed_date = datetime.utcnow()
    appointment.changed_by_user_id = user.id


def create_photo(
    db: Session,
    appointment: models.Appointment,
    address: models.Address,
    photo_type: str,
    filename: str,
    data: bytes,
    user: models.User,
) -> None:
    if photo_type not in ALLOWED_TYPES:
        return
    file_path = save_zip_photo(address, photo_type, filename, data)
    db.add(
        models.AppointmentPhoto(
            appointment_id=appointment.id,
            address_id=address.id,
            file_path=file_path,
            photo_type=photo_type,
            uploaded_by_user_id=user.id,
        )
    )


@router.get("")
def import_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    return request.app.state.templates.TemplateResponse(
        "admin_completed_import.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
        },
    )


@router.get("/export")
def export_completed(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    rows = (
        db.query(models.Appointment, models.Address, models.User)
        .join(models.Address, models.Address.id == models.Appointment.address_id)
        .join(models.User, models.User.id == models.Appointment.contractor_id)
        .filter(
            models.Appointment.status.in_(
                [
                    models.AppointmentStatus.CLOSED,
                    models.AppointmentStatus.COMPLETED,
                ]
            )
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )
    if not rows:
        flash(request, "Ingen afsluttede import-sager", "error")
        return RedirectResponse("/admin/import/completed", status_code=303)

    photos = (
        db.query(models.AppointmentPhoto)
        .filter(
            models.AppointmentPhoto.appointment_id.in_([row[0].id for row in rows])
        )
        .all()
    )
    photo_map: dict[int, dict[str, list[str]]] = {}
    for photo in photos:
        photo_map.setdefault(photo.appointment_id, {"both": [], "new": [], "old": []})
        if photo.photo_type in ALLOWED_TYPES:
            photo_map[photo.appointment_id][photo.photo_type].append(photo.file_path)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "street",
            "house_no",
            "zip",
            "city",
            "changed_date",
            "vvs_name",
            "status",
            "old_meter_no",
            "new_meter_no",
            "photo_both",
            "photo_new",
            "photo_old",
        ]
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for appointment, address, vvs_user in rows:
            changed_date = appointment.starts_at.date().isoformat()
            photo_lists = photo_map.get(appointment.id, {"both": [], "new": [], "old": []})
            writer.writerow(
                [
                    address.street,
                    address.house_no,
                    address.zip,
                    address.city,
                    changed_date,
                    vvs_user.username,
                    appointment.status.value,
                    appointment.old_meter_no or "",
                    appointment.new_meter_no or "",
                    ";".join(photo_lists["both"]),
                    ";".join(photo_lists["new"]),
                    ";".join(photo_lists["old"]),
                ]
            )

            for photo_path in photo_lists["both"] + photo_lists["new"] + photo_lists["old"]:
                full_path = (UPLOAD_DIR / photo_path).resolve()
                if full_path.exists():
                    archive.write(full_path, arcname=photo_path)

        archive.writestr("completed.csv", output.getvalue())

    filename = "completed_export.zip"
    return Response(
        zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("")
def import_completed(
    request: Request,
    csv_file: UploadFile = File(...),
    zip_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    try:
        raw = csv_file.file.read()
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        flash(request, "CSV-filen kunne ikke læses", "error")
        return RedirectResponse("/admin/import/completed", status_code=303)

    required_fields = {
        "street",
        "house_no",
        "zip",
        "city",
        "changed_date",
        "vvs_name",
    }
    if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
        flash(request, "CSV skal indeholde street, house_no, zip, city, changed_date, vvs_name", "error")
        return RedirectResponse("/admin/import/completed", status_code=303)

    zip_entries = read_zip(zip_file)
    created = 0
    skipped = 0
    skipped_existing_availability = 0
    photos_added = 0
    created_availability: set[tuple[int, date]] = set()

    for row in reader:
        street = (row.get("street") or "").strip()
        house_no = (row.get("house_no") or "").strip()
        zip_code = (row.get("zip") or "").strip()
        city = (row.get("city") or "").strip()
        changed_raw = (row.get("changed_date") or "").strip()
        vvs_name = (row.get("vvs_name") or "").strip()
        status_raw = (row.get("status") or "").strip().lower()
        if not all([street, house_no, zip_code, city, changed_raw, vvs_name]):
            skipped += 1
            continue

        if status_raw and status_raw not in ALLOWED_STATUSES:
            skipped += 1
            continue

        address = resolve_address(db, street, house_no, zip_code, city)
        if not address:
            skipped += 1
            continue

        vvs_user = resolve_vvs(db, vvs_name)
        if not vvs_user:
            skipped += 1
            continue

        try:
            changed_date = parse_date(changed_raw)
        except ValueError:
            skipped += 1
            continue

        availability_date = changed_date.date()
        availability_key = (vvs_user.id, availability_date)
        if availability_key not in created_availability:
            existing_availability = (
                db.query(models.VvsAvailability)
                .filter(
                    models.VvsAvailability.user_id == vvs_user.id,
                    models.VvsAvailability.date == availability_date,
                )
                .first()
            )
            if existing_availability:
                skipped += 1
                skipped_existing_availability += 1
                continue

            db.add(
                models.VvsAvailability(
                    user_id=vvs_user.id,
                    date=availability_date,
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                )
            )
            db.flush()
            created_availability.add(availability_key)

        status_value = status_raw or "closed"

        appointment = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.address_id == address.id,
                models.Appointment.status == models.AppointmentStatus.CLOSED,
            )
            .first()
        )
        if not appointment:
            appointment = models.Appointment(
                address_id=address.id,
                contractor_id=vvs_user.id,
                starts_at=changed_date,
                ends_at=changed_date + timedelta(minutes=30),
                status=STATUS_MAP[status_value],
                changed_date=datetime.utcnow(),
                changed_by_user_id=user.id,
            )
            db.add(appointment)
            db.flush()

        appointment.status = STATUS_MAP[status_value]
        appointment.changed_date = datetime.utcnow()
        appointment.changed_by_user_id = user.id

        for filename in parse_photo_list(row.get("photo_both") or ""):
            data = zip_entries.get(filename)
            if data:
                create_photo(db, appointment, address, "both", filename, data, user)
                photos_added += 1
        for filename in parse_photo_list(row.get("photo_new") or ""):
            data = zip_entries.get(filename)
            if data:
                create_photo(db, appointment, address, "new", filename, data, user)
                photos_added += 1
        for filename in parse_photo_list(row.get("photo_old") or ""):
            data = zip_entries.get(filename)
            if data:
                create_photo(db, appointment, address, "old", filename, data, user)
                photos_added += 1

        if status_value == "closed":
            ensure_closed(appointment, user)
        created += 1

    db.commit()
    skip_detail = ""
    if skipped_existing_availability:
        skip_detail = f" ({skipped_existing_availability} pga. eksisterende arbejdsdag)"
    flash(
        request,
        f"Importerede {created} sager. {photos_added} fotos tilføjet. {skipped} rækker sprunget over{skip_detail}.",
        "success",
    )
    return RedirectResponse("/admin/import/completed", status_code=303)
