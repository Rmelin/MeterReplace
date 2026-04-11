from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role

router = APIRouter(prefix="/admin/messages", tags=["admin"])

RESPONSE_LABELS = {
    "reschedule_request": "Tidspunkt passer ikke",
    "buffer_note": "Målerbrønd angivet",
    "confirm_time": "Tidspunkt bekræftet",
}

FILTERS = [
    {"value": "all", "label": "Alle"},
    {"value": "reschedule_request", "label": "Tidspunkt passer ikke"},
    {"value": "buffer_note", "label": "Målerbrønd angivet"},
    {"value": "confirm_time", "label": "Tidspunkt bekræftet"},
]


@router.get("")
def message_dashboard(
    request: Request,
    response_type: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    selected_type = response_type or "all"
    allowed_types = {item["value"] for item in FILTERS}
    if selected_type not in allowed_types:
        return RedirectResponse("/admin/messages", status_code=303)

    query = (
        db.query(models.ResidentResponse, models.Address)
        .join(models.Address, models.Address.id == models.ResidentResponse.address_id)
        .filter(models.ResidentResponse.message.is_not(None))
        .filter(models.ResidentResponse.message != "")
    )
    if selected_type != "all":
        query = query.filter(models.ResidentResponse.response_type == selected_type)

    rows = (
        query.order_by(models.ResidentResponse.created_at.desc())
        .all()
    )
    cutoff = datetime.utcnow() - timedelta(days=7)

    messages = []
    for response, address in rows:
        messages.append(
            {
                "id": response.id,
                "created_at": response.created_at,
                "type": response.response_type,
                "type_label": RESPONSE_LABELS.get(response.response_type, "Svar modtaget"),
                "message": response.message or "",
                "address": address,
                "channel": "Brevlink/QR",
                "is_old": response.created_at < cutoff,
            }
        )

    return request.app.state.templates.TemplateResponse(
        "admin_messages.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "messages": messages,
            "filters": FILTERS,
            "selected_type": selected_type,
        },
    )
