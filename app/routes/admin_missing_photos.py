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


@router.get("")
def missing_photos_overview(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    photo_address_ids = {
        row[0]
        for row in db.query(models.AppointmentPhoto.address_id).distinct().all()
    }
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
        if address.id in photo_address_ids:
            continue
        rows.append(
            {
                "appointment": appointment,
                "address": address,
                "contractor": contractor,
            }
        )

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
