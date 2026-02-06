from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash

router = APIRouter(prefix="/r", tags=["resident"])


def find_link(db: Session, token: str) -> models.ResidentLink | None:
    return db.query(models.ResidentLink).filter(models.ResidentLink.token == token).first()


def scheduled_appointment(db: Session, address_id: int) -> models.Appointment | None:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id == address_id,
            models.Appointment.status.in_(
                [
                    models.AppointmentStatus.SCHEDULED,
                    models.AppointmentStatus.INFORMED,
                ]
            ),
        )
        .order_by(models.Appointment.starts_at.desc())
        .first()
    )


def release_stock(db: Session, note: str) -> None:
    db.add(
        models.StockMovement(
            movement_type=models.InventoryMovementType.RELEASE,
            quantity=1,
            note=note,
        )
    )


@router.get("/{token}")
def resident_form(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    link = find_link(db, token)
    if not link:
        raise HTTPException(status_code=404, detail="Link ikke fundet")

    address = db.query(models.Address).filter(models.Address.id == link.address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    appointment = scheduled_appointment(db, address.id)

    if not link.active:
        return request.app.state.templates.TemplateResponse(
            "resident_response_done.html",
            {
                "request": request,
                "current_user": None,
                "flashes": consume_flashes(request),
                "address": address,
                "message": "Tak! Vi har allerede modtaget dit svar.",
            },
        )

    return request.app.state.templates.TemplateResponse(
        "resident_response_form.html",
        {
            "request": request,
            "current_user": None,
            "flashes": consume_flashes(request),
            "address": address,
            "appointment": appointment,
            "token": token,
        },
    )


@router.post("/{token}")
def resident_submit(
    request: Request,
    token: str,
    response_type: str = Form(""),
    message: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    link = find_link(db, token)
    if not link:
        raise HTTPException(status_code=404, detail="Link ikke fundet")

    address = db.query(models.Address).filter(models.Address.id == link.address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    if not link.active:
        return RedirectResponse(f"/r/{token}", status_code=303)

    response_type = response_type.strip()
    message = message.strip() or None
    phone = phone.strip() or None
    email = email.strip() or None
    if phone:
        address.customer_phone = phone
    if email:
        address.customer_email = email

    if response_type not in {"buffer_note", "reschedule_request"}:
        flash(request, "Vælg en gyldig type", "error")
        return RedirectResponse(f"/r/{token}", status_code=303)

    appointment = scheduled_appointment(db, address.id)

    if response_type == "buffer_note":
        if not message:
            flash(request, "Angiv placering af målerbrønd", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        address.buffer_flag = True
        address.buffer_note = message

    if response_type == "reschedule_request":
        if appointment:
            appointment.status = models.AppointmentStatus.NEEDS_RESCHEDULE
            appointment.changed_date = datetime.utcnow()
            appointment.changed_by_user_id = None
            release_stock(db, f"Beboer ønsker nyt tidspunkt {address.street} {address.house_no}")

    db.add(
        models.ResidentResponse(
            address_id=address.id,
            appointment_id=appointment.id if appointment else None,
            response_type=response_type,
            message=message,
            phone=phone,
            email=email,
            created_at=datetime.utcnow(),
        )
    )

    link.active = False
    db.commit()

    return request.app.state.templates.TemplateResponse(
        "resident_response_done.html",
        {
            "request": request,
            "current_user": None,
            "flashes": consume_flashes(request),
            "address": address,
            "message": "Tak! Vi har modtaget dit svar.",
        },
    )
