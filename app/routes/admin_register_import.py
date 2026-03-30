from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/import/register", tags=["admin"])

LOG_DIR = Path("data") / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def resolve_address(
    db: Session, street: str, house_no: str, zip_code: str, city: str
) -> models.Address | None:
    return (
        db.query(models.Address)
        .filter(
            func.lower(models.Address.street) == street.lower(),
            func.lower(models.Address.house_no) == house_no.lower(),
            func.lower(models.Address.zip) == zip_code.lower(),
            func.lower(models.Address.city) == city.lower(),
        )
        .first()
    )


@router.get("")
def import_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    return request.app.state.templates.TemplateResponse(
        "admin_register_import.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
        },
    )


@router.post("")
def import_register(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    try:
        raw = file.file.read()
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        flash(request, "CSV-filen kunne ikke læses", "error")
        return RedirectResponse("/admin/import/register", status_code=303)

    if not reader.fieldnames:
        flash(request, "CSV-filen mangler header", "error")
        return RedirectResponse("/admin/import/register", status_code=303)

    fieldnames = set(reader.fieldnames)
    required_fields = {"street", "house_no", "zip", "city"}
    has_meter = "new_meter_no" in fieldnames or "meter_no" in fieldnames
    if not required_fields.issubset(fieldnames) or not has_meter:
        flash(
            request,
            "CSV skal indeholde street, house_no, zip, city samt meter_no eller new_meter_no",
            "error",
        )
        return RedirectResponse("/admin/import/register", status_code=303)

    total = 0
    updated = 0
    skipped = 0
    log_rows: list[tuple[str, str, str, str, str, str]] = []

    for row in reader:
        total += 1
        street = (row.get("street") or "").strip()
        house_no = (row.get("house_no") or "").strip()
        zip_code = (row.get("zip") or "").strip()
        city = (row.get("city") or "").strip()
        meter_value = (row.get("new_meter_no") or row.get("meter_no") or "").strip()

        if not all([street, house_no, zip_code, city]):
            skipped += 1
            log_rows.append(
                (street, house_no, zip_code, city, meter_value, "Adresse mangler")
            )
            continue
        if not meter_value:
            skipped += 1
            log_rows.append(
                (street, house_no, zip_code, city, meter_value, "Ny målernr. mangler")
            )
            continue

        address = resolve_address(db, street, house_no, zip_code, city)
        if not address:
            skipped += 1
            log_rows.append(
                (street, house_no, zip_code, city, meter_value, "Adresse findes ikke")
            )
            continue

        appointment = (
            db.query(models.Appointment)
            .filter(models.Appointment.address_id == address.id)
            .order_by(models.Appointment.starts_at.desc())
            .first()
        )
        address.new_meter_no = meter_value
        address.register_closed = True
        if appointment:
            appointment.status = models.AppointmentStatus.CLOSED
            appointment.changed_date = datetime.utcnow()
            appointment.changed_by_user_id = user.id
        else:
            log_rows.append(
                (
                    street,
                    house_no,
                    zip_code,
                    city,
                    meter_value,
                    "Afsluttet uden aftale",
                )
            )
        updated += 1

    if updated:
        db.commit()

    log_filename = None
    if log_rows:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        log_filename = f"register-import-{timestamp}.csv"
        log_path = LOG_DIR / log_filename
        with log_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["street", "house_no", "zip", "city", "meter_no", "Fejl"])
            writer.writerows(log_rows)

    if log_filename:
        flash(
            request,
            f"Importerede {total} rækker, opdaterede {updated}, skippede {skipped}. Log: {log_filename}",
            "success",
        )
    else:
        flash(
            request,
            f"Importerede {total} rækker, opdaterede {updated}, skippede {skipped}.",
            "success",
        )

    return RedirectResponse("/admin/import/register", status_code=303)
