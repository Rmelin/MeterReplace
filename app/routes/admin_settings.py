from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.app_settings import DEFAULT_PLANNING_NOTICE_DAYS, planning_notice_days, set_setting_value
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/settings", tags=["admin"])


@router.get("")
@router.get("/")
def settings_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    return request.app.state.templates.TemplateResponse(
        "admin_settings.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "planning_notice_days": planning_notice_days(db),
            "default_planning_notice_days": DEFAULT_PLANNING_NOTICE_DAYS,
        },
    )


@router.post("")
@router.post("/")
def settings_save(
    request: Request,
    planning_notice_days_value: int = Form(DEFAULT_PLANNING_NOTICE_DAYS),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    del user
    if planning_notice_days_value < 0:
        flash(request, "Varslingsperiode skal være 0 eller højere", "error")
        return RedirectResponse("/admin/settings", status_code=303)

    set_setting_value(db, "planning_notice_days", str(planning_notice_days_value))
    db.commit()
    flash(request, "Indstillinger gemt", "success")
    return RedirectResponse("/admin/settings", status_code=303)
