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


def normalize_header(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(".", "")
        .replace(" ", "")
        .replace("_", "")
    )


def parse_register_address(value: str) -> tuple[str, str, str, str] | None:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        return None
    street, house_no, zip_code, city = parts
    if not all([street, house_no, zip_code, city]):
        return None
    return street, house_no, zip_code, city


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
        reader = csv.DictReader(io.StringIO(content), delimiter=";")
    except Exception:
        flash(request, "CSV-filen kunne ikke læses", "error")
        return RedirectResponse("/admin/import/register", status_code=303)

    if not reader.fieldnames:
        flash(request, "CSV-filen mangler header", "error")
        return RedirectResponse("/admin/import/register", status_code=303)

    normalized = {normalize_header(name): name for name in reader.fieldnames}
    address_key = normalized.get("adresse")
    meter_key = normalized.get("maalernr") or normalized.get("målernr")

    if not address_key or not meter_key:
        flash(request, "CSV header skal være: Adresse;Målernr.", "error")
        return RedirectResponse("/admin/import/register", status_code=303)

    total = 0
    updated = 0
    skipped = 0
    log_rows: list[tuple[str, str, str]] = []

    for row in reader:
        total += 1
        address_value = (row.get(address_key) or "").strip()
        meter_value = (row.get(meter_key) or "").strip()

        if not address_value:
            skipped += 1
            log_rows.append((address_value, meter_value, "Adresse mangler"))
            continue
        if not meter_value:
            skipped += 1
            log_rows.append((address_value, meter_value, "Målernr. mangler"))
            continue

        parsed = parse_register_address(address_value)
        if not parsed:
            skipped += 1
            log_rows.append((address_value, meter_value, "Adresseformat er ugyldigt"))
            continue
        street, house_no, zip_code, city = parsed

        address = resolve_address(db, street, house_no, zip_code, city)
        if not address:
            skipped += 1
            log_rows.append((address_value, meter_value, "Adresse findes ikke"))
            continue

        appointment = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.address_id == address.id,
                models.Appointment.status.in_(
                    [
                        models.AppointmentStatus.COMPLETED,
                        models.AppointmentStatus.CLOSED,
                    ]
                ),
            )
            .order_by(models.Appointment.starts_at.desc())
            .first()
        )
        if not appointment:
            skipped += 1
            log_rows.append(
                (address_value, meter_value, "Adresse mangler status Skiftet")
            )
            continue

        address.new_meter_no = meter_value
        if appointment.status == models.AppointmentStatus.COMPLETED:
            appointment.status = models.AppointmentStatus.CLOSED
            appointment.changed_date = datetime.utcnow()
            appointment.changed_by_user_id = user.id
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
            writer.writerow(["Adresse", "Målernr.", "Fejl"])
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
