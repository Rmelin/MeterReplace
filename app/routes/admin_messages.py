from __future__ import annotations


from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role
from app.timeutils import utc_now

router = APIRouter(prefix="/admin/messages", tags=["admin"])

RESPONSE_LABELS = {
    "reschedule_request": "Tidspunkt passer ikke",
    "buffer_note": "Målerbrønd angivet",
    "confirm_time": "Tidspunkt bekræftet",
    "message": "Anden besked",
}

FILTERS = [
    {"value": "all", "label": "Alle"},
    {"value": "reschedule_request", "label": "Tidspunkt passer ikke"},
    {"value": "buffer_note", "label": "Målerbrønd angivet"},
    {"value": "confirm_time", "label": "Tidspunkt bekræftet"},
    {"value": "message", "label": "Anden besked"},
]

FOLDERS = [
    {"value": "new", "label": "Ny", "status": models.ResidentMessageStatus.NEW},
    {"value": "todo", "label": "Todo", "status": models.ResidentMessageStatus.TODO},
    {"value": "read", "label": "Læst", "status": models.ResidentMessageStatus.READ},
    {
        "value": "archived",
        "label": "Arkiv",
        "status": models.ResidentMessageStatus.ARCHIVED,
    },
]

STATUS_LABELS = {
    models.ResidentMessageStatus.NEW: "Ny",
    models.ResidentMessageStatus.TODO: "Todo",
    models.ResidentMessageStatus.READ: "Læst",
    models.ResidentMessageStatus.ARCHIVED: "Arkiv",
}

APPOINTMENT_STATUS_LABELS = {
    models.AppointmentStatus.DRAFT: "Kladde",
    models.AppointmentStatus.NOT_SCHEDULED: "Ikke planlagt",
    models.AppointmentStatus.SCHEDULED: "Planlagt",
    models.AppointmentStatus.INFORMED: "Beboer/kunde informeret",
    models.AppointmentStatus.COMPLETED: "Skiftet",
    models.AppointmentStatus.CLOSED: "Afsluttet",
    models.AppointmentStatus.NOT_HOME: "Ikke hjemme",
    models.AppointmentStatus.NEEDS_RESCHEDULE: "Behov for ny dato",
}


def dashboard_url(folder: str, response_type: str) -> str:
    params = {}
    if folder != "new":
        params["folder"] = folder
    if response_type != "all":
        params["response_type"] = response_type
    query = urlencode(params)
    return f"/admin/messages?{query}" if query else "/admin/messages"


@router.get("")
def message_dashboard(
    request: Request,
    folder: str | None = None,
    response_type: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    selected_folder = folder or "new"
    selected_type = response_type or "all"
    folder_map = {item["value"]: item["status"] for item in FOLDERS}
    if selected_folder not in folder_map:
        return RedirectResponse("/admin/messages", status_code=303)
    allowed_types = {item["value"] for item in FILTERS}
    if selected_type not in allowed_types:
        return RedirectResponse("/admin/messages", status_code=303)

    count_rows = (
        db.query(
            models.ResidentResponse.mailbox_status,
            func.count(models.ResidentResponse.id),
        )
        .filter(models.ResidentResponse.mailbox_status.is_not(None))
        .group_by(models.ResidentResponse.mailbox_status)
        .all()
    )
    status_counts = {status: count for status, count in count_rows}
    folders = [
        {
            **item,
            "count": status_counts.get(item["status"], 0),
            "href": dashboard_url(item["value"], selected_type),
        }
        for item in FOLDERS
    ]
    filters = [
        {
            **item,
            "href": dashboard_url(selected_folder, item["value"]),
        }
        for item in FILTERS
    ]

    query = (
        db.query(models.ResidentResponse, models.Address)
        .join(models.Address, models.Address.id == models.ResidentResponse.address_id)
        .filter(models.ResidentResponse.mailbox_status == folder_map[selected_folder])
    )
    if selected_type != "all":
        query = query.filter(models.ResidentResponse.response_type == selected_type)

    rows = query.order_by(models.ResidentResponse.created_at.desc()).all()

    # A response normally stores the appointment it relates to.  Older responses
    # may not, so use the latest appointment for that address as a useful fallback.
    appointment_ids = {response.appointment_id for response, _address in rows if response.appointment_id}
    appointments_by_id = {}
    if appointment_ids:
        appointments_by_id = {
            appointment.id: appointment
            for appointment in db.query(models.Appointment)
            .filter(models.Appointment.id.in_(appointment_ids))
            .all()
        }

    address_ids_without_appointment = {
        address.id
        for response, address in rows
        if response.appointment_id is None
    }
    latest_appointments_by_address = {}
    if address_ids_without_appointment:
        for appointment in (
            db.query(models.Appointment)
            .filter(models.Appointment.address_id.in_(address_ids_without_appointment))
            .order_by(models.Appointment.address_id, models.Appointment.starts_at.desc())
            .all()
        ):
            latest_appointments_by_address.setdefault(appointment.address_id, appointment)

    messages = []
    for response, address in rows:
        appointment = appointments_by_id.get(response.appointment_id)
        if appointment is None:
            appointment = latest_appointments_by_address.get(address.id)
        appointment_label = "Ikke planlagt"
        if appointment:
            appointment_label = APPOINTMENT_STATUS_LABELS[appointment.status]
            if appointment.status != models.AppointmentStatus.NOT_SCHEDULED:
                appointment_label += " · " + appointment.starts_at.strftime("%d/%m/%Y %H:%M")
        messages.append(
            {
                "id": response.id,
                "created_at": response.created_at,
                "type": response.response_type,
                "type_label": RESPONSE_LABELS.get(response.response_type, "Svar modtaget"),
                "message": response.message or "",
                "answer": response.answer,
                "address": address,
                "channel": "Brevlink/QR",
                "status": response.mailbox_status,
                "status_label": STATUS_LABELS[response.mailbox_status],
                "appointment_label": appointment_label,
            }
        )

    return request.app.state.templates.TemplateResponse(
        "admin_messages.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "messages": messages,
            "folders": folders,
            "filters": filters,
            "statuses": STATUS_LABELS,
            "selected_folder": selected_folder,
            "selected_type": selected_type,
        },
    )


@router.post("/{response_id}/status")
def update_message_status(
    request: Request,
    response_id: int,
    mailbox_status: str = Form(...),
    folder: str = Form("new"),
    response_type: str = Form("all"),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    allowed_statuses = {status.value: status for status in STATUS_LABELS}
    status = allowed_statuses.get(mailbox_status)
    if status is None:
        raise HTTPException(status_code=400, detail="Ugyldig beskedstatus")

    response = (
        db.query(models.ResidentResponse)
        .filter(
            models.ResidentResponse.id == response_id,
            models.ResidentResponse.mailbox_status.is_not(None),
        )
        .first()
    )
    if not response:
        raise HTTPException(status_code=404, detail="Besked ikke fundet")

    response.mailbox_status = status
    response.mailbox_status_updated_at = utc_now()
    response.mailbox_status_updated_by_user_id = user.id
    db.commit()
    flash(request, f"Beskeden er flyttet til {STATUS_LABELS[status]}", "success")

    valid_folders = {item["value"] for item in FOLDERS}
    valid_types = {item["value"] for item in FILTERS}
    return RedirectResponse(
        dashboard_url(
            folder if folder in valid_folders else "new",
            response_type if response_type in valid_types else "all",
        ),
        status_code=303,
    )
