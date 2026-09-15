from __future__ import annotations

from datetime import datetime, time, timedelta
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash
from app.push_notifications import enqueue_message_pushes

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


def appointment_for_link(
    db: Session, link: models.ResidentLink
) -> models.Appointment | None:
    if link.appointment_id:
        return (
            db.query(models.Appointment)
            .filter(
                models.Appointment.id == link.appointment_id,
                models.Appointment.address_id == link.address_id,
            )
            .first()
        )
    appointment = scheduled_appointment(db, link.address_id)
    if appointment:
        link.appointment_id = appointment.id
        db.commit()
    return appointment


def latest_link_response(
    db: Session,
    link_id: int,
    response_types: tuple[str, ...],
) -> models.ResidentResponse | None:
    return (
        db.query(models.ResidentResponse)
        .filter(
            models.ResidentResponse.resident_link_id == link_id,
            models.ResidentResponse.response_type.in_(response_types),
        )
        .order_by(
            models.ResidentResponse.created_at.desc(),
            models.ResidentResponse.id.desc(),
        )
        .first()
    )


def resident_form_context(
    db: Session,
    link: models.ResidentLink,
) -> dict[str, object]:
    return {
        "meter_pit_response": latest_link_response(db, link.id, ("buffer_note",)),
        "time_response": latest_link_response(
            db, link.id, ("confirm_time", "reschedule_request")
        ),
        "messages": (
            db.query(models.ResidentResponse)
            .filter(
                models.ResidentResponse.resident_link_id == link.id,
                models.ResidentResponse.response_type == "message",
            )
            .order_by(models.ResidentResponse.created_at.desc())
            .limit(10)
            .all()
        ),
    }


def valid_request_id(value: str) -> bool:
    return re.fullmatch(r"[a-f0-9]{32}", value) is not None


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

    if not link.active:
        raise HTTPException(status_code=404, detail="Link ikke fundet")

    appointment = appointment_for_link(db, link)
    responses = resident_form_context(db, link)

    return request.app.state.templates.TemplateResponse(
        "resident_response_form.html",
        {
            "request": request,
            "current_user": None,
            "flashes": consume_flashes(request),
            "address": address,
            "appointment": appointment,
            "token": token,
            "saved": request.query_params.get("saved"),
            "contact_request_id": uuid4().hex,
            "meter_pit_request_id": uuid4().hex,
            "time_request_id": uuid4().hex,
            "message_request_id": uuid4().hex,
            "can_answer_time": bool(
                appointment
                and appointment.status
                in {
                    models.AppointmentStatus.SCHEDULED,
                    models.AppointmentStatus.INFORMED,
                    models.AppointmentStatus.NEEDS_RESCHEDULE,
                }
            ),
            **responses,
        },
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post("/{token}")
def resident_submit(
    request: Request,
    token: str,
    intent: str = Form(""),
    request_id: str = Form(""),
    answer: str = Form(""),
    message: str = Form(""),
    name: str | None = Form(""),
    phone: str | None = Form(""),
    email: str | None = Form(""),
    db: Session = Depends(get_db),
):
    link = find_link(db, token)
    if not link:
        raise HTTPException(status_code=404, detail="Link ikke fundet")

    address = db.query(models.Address).filter(models.Address.id == link.address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    if not link.active:
        raise HTTPException(status_code=404, detail="Link ikke fundet")

    intent = intent.strip().lower()
    request_id = request_id.strip().lower()
    answer = answer if isinstance(answer, str) else ""
    message = message if isinstance(message, str) else ""
    answer = answer.strip().lower()
    message_value = message.strip() or None
    name = name if isinstance(name, str) else ""
    name = name.strip() or None
    phone = phone if isinstance(phone, str) else ""
    email = email if isinstance(email, str) else ""
    phone = phone.strip() or None
    email = email.strip() or None

    if not valid_request_id(request_id):
        flash(request, "Formularen er udløbet. Prøv igen.", "error")
        return RedirectResponse(f"/r/{token}", status_code=303)
    existing = (
        db.query(models.ResidentResponse)
        .filter(models.ResidentResponse.request_id == request_id)
        .first()
    )
    if existing:
        return RedirectResponse(f"/r/{token}?saved={intent}", status_code=303)
    if intent not in {"contact", "meter_pit", "time", "message"}:
        flash(request, "Vælg hvad du vil sende", "error")
        return RedirectResponse(f"/r/{token}", status_code=303)
    if (
        len(message_value or "") > 4000
        or len(name or "") > 200
        or len(phone or "") > 50
        or len(email or "") > 200
    ):
        flash(request, "Beskeden eller kontaktoplysningerne er for lange", "error")
        return RedirectResponse(f"/r/{token}", status_code=303)
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        flash(request, "E-mailadressen er ugyldig", "error")
        return RedirectResponse(f"/r/{token}", status_code=303)

    appointment = appointment_for_link(db, link)
    submitted_at = datetime.utcnow()
    response_type: str
    mailbox_status: models.ResidentMessageStatus | None = None

    if intent == "contact":
        address.customer_name = name
        address.customer_phone = phone
        address.customer_email = email
        response_type = "contact_update"
        answer = ""
        message_value = "Kontaktoplysninger opdateret"
    elif intent == "meter_pit":
        if answer not in {"yes", "no"}:
            flash(request, "Vælg ja eller nej til målerbrønd", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        if answer == "yes" and not message_value:
            flash(request, "Angiv placering af målerbrønd", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        if len(message_value or "") > 255:
            flash(request, "Placeringen må højst være 255 tegn", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        address.buffer_flag = answer == "yes"
        address.buffer_note = message_value if answer == "yes" else None
        response_type = "buffer_note"
        mailbox_status = models.ResidentMessageStatus.NEW
    elif intent == "time":
        if answer not in {"yes", "same_day", "new_day"}:
            flash(request, "Vælg en af de tre muligheder for aftalen", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        if not appointment:
            flash(request, "Der er ikke længere en aftale på dette link", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        if answer == "same_day":
            if not message_value:
                flash(
                    request,
                    "Angiv hvornår du kan være hjemme eller ikke er hjemme",
                    "error",
                )
                return RedirectResponse(f"/r/{token}", status_code=303)
            message_value = f"Den planlagte dag passer. {message_value}"
        previous = latest_link_response(
            db, link.id, ("confirm_time", "reschedule_request")
        )
        response_type = "confirm_time" if answer == "yes" else "reschedule_request"
        transitioned = 0
        if answer != "yes":
            transitioned = (
                db.query(models.Appointment)
                .filter(
                    models.Appointment.id == appointment.id,
                    models.Appointment.status.in_(
                        {
                            models.AppointmentStatus.SCHEDULED,
                            models.AppointmentStatus.INFORMED,
                        }
                    ),
                )
                .update(
                    {
                        "status": models.AppointmentStatus.NEEDS_RESCHEDULE,
                        "changed_date": datetime.utcnow(),
                        "changed_by_user_id": None,
                    },
                    synchronize_session=False,
                )
            )
        if transitioned == 1:
            release_stock(db, f"Beboer ønsker nyt tidspunkt {address.street} {address.house_no}")
            if answer == "new_day":
                day = appointment.starts_at.date()
                starts_at = datetime.combine(day, time(8, 0))
                ends_at = datetime.combine(day, time(16, 0))
                db.add(
                    models.AddressUnavailablePeriod(
                        address_id=address.id,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        note=(message_value or "Beboer har ikke tid denne dag"),
                    )
                )
        if answer != "yes" or message_value or (previous and previous.answer != answer):
            mailbox_status = models.ResidentMessageStatus.NEW
    else:
        if not message_value:
            flash(request, "Skriv en besked", "error")
            return RedirectResponse(f"/r/{token}", status_code=303)
        response_type = "message"
        answer = ""
        mailbox_status = models.ResidentMessageStatus.NEW

    response = models.ResidentResponse(
        address_id=address.id,
        appointment_id=appointment.id if appointment else None,
        resident_link_id=link.id,
        response_type=response_type,
        answer=answer or None,
        request_id=request_id,
        message=message_value,
        phone=phone,
        email=email,
        mailbox_status=mailbox_status,
        mailbox_status_updated_at=submitted_at if mailbox_status else None,
        created_at=submitted_at,
    )
    db.add(response)
    if mailbox_status:
        enqueue_message_pushes(db, response)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/r/{token}?saved={intent}", status_code=303)

    return RedirectResponse(f"/r/{token}?saved={intent}", status_code=303)
