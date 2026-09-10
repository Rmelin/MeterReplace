from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role

router = APIRouter(prefix="/admin/missing-photos", tags=["admin"])

STATUS_LABELS = {
    models.AppointmentStatus.COMPLETED: "Skiftet",
    models.AppointmentStatus.CLOSED: "Afsluttet",
}


def photo_complete(photos: list[models.AppointmentPhoto]) -> bool:
    photo_types = {photo.photo_type for photo in photos}
    return "both" in photo_types or {"new", "old"}.issubset(photo_types)


def missing_photo_rows(db: Session) -> list[dict[str, object]]:
    photos = db.query(models.AppointmentPhoto).all()
    photos_by_appointment: dict[int, list[models.AppointmentPhoto]] = {}
    photo_address_ids: set[int] = set()
    for photo in photos:
        photos_by_appointment.setdefault(photo.appointment_id, []).append(photo)
        photo_address_ids.add(photo.address_id)

    appointments = (
        db.query(models.Appointment, models.Address, models.User)
        .join(models.Address, models.Address.id == models.Appointment.address_id)
        .join(models.User, models.User.id == models.Appointment.contractor_id)
        .filter(
            models.Appointment.status.in_(
                [models.AppointmentStatus.COMPLETED, models.AppointmentStatus.CLOSED]
            )
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )

    seen_addresses: set[int] = set()
    rows: list[dict[str, object]] = []
    for appointment, address, contractor in appointments:
        if address.id in seen_addresses:
            continue
        seen_addresses.add(address.id)
        if photo_complete(photos_by_appointment.get(appointment.id, [])):
            continue
        rows.append(
            {
                "appointment": appointment,
                "address": address,
                "contractor": contractor,
            }
        )

    register_closed_addresses = (
        db.query(models.Address)
        .filter(models.Address.register_closed.is_(True))
        .order_by(models.Address.street, models.Address.house_no)
        .all()
    )
    for address in register_closed_addresses:
        if address.id in seen_addresses or address.id in photo_address_ids:
            continue
        rows.append(
            {
                "appointment": None,
                "address": address,
                "contractor": None,
            }
        )
    return rows


@router.get("")
def missing_photos_overview(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    rows = missing_photo_rows(db)

    return request.app.state.templates.TemplateResponse(
        "admin_missing_photos.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "rows": rows,
            "status_labels": STATUS_LABELS,
        },
    )
