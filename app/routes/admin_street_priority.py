from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/street-priority", tags=["admin"])


def fetch_street_list(db: Session) -> list[str]:
    rows = db.query(models.Address.street).distinct().order_by(models.Address.street).all()
    return [row[0] for row in rows]


def fetch_priority_map(db: Session) -> dict[str, models.StreetPriority]:
    rows = db.query(models.StreetPriority).all()
    return {row.street.lower(): row for row in rows}


def all_streets(db: Session) -> list[str]:
    address_streets = fetch_street_list(db)
    priority_rows = db.query(models.StreetPriority.street).distinct().all()
    priority_streets = [row[0] for row in priority_rows]
    return sorted({*address_streets, *priority_streets})


@router.get("")
def street_priority_overview(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    streets = fetch_street_list(db)
    priorities = (
        db.query(models.StreetPriority)
        .order_by(models.StreetPriority.priority.desc(), models.StreetPriority.street)
        .all()
    )
    return request.app.state.templates.TemplateResponse(
        "admin_street_priority.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "streets": streets,
            "priorities": priorities,
        },
    )


@router.post("")
def set_priority(
    request: Request,
    street: str = Form(""),
    priority: int = Form(0),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    street = street.strip()
    if not street:
        flash(request, "Vælg en vej", "error")
        return RedirectResponse("/admin/street-priority", status_code=303)

    if priority < 0:
        flash(request, "Prioritet skal være 0 eller højere", "error")
        return RedirectResponse("/admin/street-priority", status_code=303)

    existing = db.query(models.StreetPriority).filter(
        func.lower(models.StreetPriority.street) == street.lower()
    ).first()

    if existing:
        existing.street = street
        existing.priority = priority
    else:
        db.add(models.StreetPriority(street=street, priority=priority))
    db.commit()

    flash(request, "Prioritet gemt", "success")
    return RedirectResponse("/admin/street-priority", status_code=303)


@router.post("/{priority_id}/delete")
def delete_priority(
    request: Request,
    priority_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    entry = db.query(models.StreetPriority).filter(models.StreetPriority.id == priority_id).first()
    if not entry:
        flash(request, "Prioritet findes ikke", "error")
        return RedirectResponse("/admin/street-priority", status_code=303)

    db.delete(entry)
    db.commit()
    flash(request, "Prioritet slettet", "success")
    return RedirectResponse("/admin/street-priority", status_code=303)


@router.get("/export")
def export_priorities(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    priority_map = fetch_priority_map(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["street", "priority"])
    for street in all_streets(db):
        priority = priority_map.get(street.lower())
        writer.writerow([street, priority.priority if priority else 0])

    filename = "street_priorities.csv"
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import")
def import_priorities(
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
        return RedirectResponse("/admin/street-priority", status_code=303)

    required_fields = {"street", "priority"}
    if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
        flash(request, "CSV skal indeholde street, priority", "error")
        return RedirectResponse("/admin/street-priority", status_code=303)

    priority_map = fetch_priority_map(db)
    created = 0
    updated = 0
    skipped = 0

    for row in reader:
        street = (row.get("street") or "").strip()
        priority_raw = (row.get("priority") or "").strip()
        if not street:
            skipped += 1
            continue
        try:
            priority_value = int(priority_raw)
        except ValueError:
            skipped += 1
            continue
        if priority_value < 0:
            skipped += 1
            continue

        key = street.lower()
        existing = priority_map.get(key)
        if existing:
            existing.street = street
            existing.priority = priority_value
            updated += 1
        else:
            db.add(models.StreetPriority(street=street, priority=priority_value))
            created += 1

    db.commit()
    flash(
        request,
        f"Importerede {created} nye og opdaterede {updated}. {skipped} sprunget over.",
        "success",
    )
    return RedirectResponse("/admin/street-priority", status_code=303)
