from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.app_settings import (
    DEFAULT_PLANNING_NOTICE_DAYS,
    SUPPORT_EMAIL_KEY,
    SUPPORT_PHONE_HOURS_KEY,
    SUPPORT_PHONE_KEY,
    planning_notice_days,
    set_setting_value,
    support_contact,
)
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/settings", tags=["admin"])


def validate_support_settings(email: str, phone: str, phone_hours: str) -> str | None:
    if len(email) > 254 or (email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        return "Supportmail er ugyldig"
    if len(phone) > 50 or (phone and not re.fullmatch(r"\+?[0-9 ()-]{5,50}", phone)):
        return "Supporttelefon er ugyldig"
    if len(phone_hours) > 255 or any(ord(char) < 32 and char not in "\t" for char in phone_hours):
        return "Telefontid er ugyldig"
    return None


@router.get("")
@router.get("/")
def settings_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    contact = support_contact(db)
    return request.app.state.templates.TemplateResponse(
        "admin_settings.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "planning_notice_days": planning_notice_days(db),
            "default_planning_notice_days": DEFAULT_PLANNING_NOTICE_DAYS,
            "support_contact": contact,
        },
    )


@router.post("")
@router.post("/")
def settings_save(
    request: Request,
    section: str = Form("planning"),
    planning_notice_days_value: int = Form(DEFAULT_PLANNING_NOTICE_DAYS),
    support_email: str = Form(""),
    support_phone: str = Form(""),
    support_phone_hours: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    del user
    if section == "support":
        email = support_email.strip()
        phone = support_phone.strip()
        phone_hours = support_phone_hours.strip()
        error = validate_support_settings(email, phone, phone_hours)
        if error:
            flash(request, error, "error")
            return RedirectResponse("/admin/settings", status_code=303)
        set_setting_value(db, SUPPORT_EMAIL_KEY, email)
        set_setting_value(db, SUPPORT_PHONE_KEY, phone)
        set_setting_value(db, SUPPORT_PHONE_HOURS_KEY, phone_hours)
        db.commit()
        flash(request, "Kontaktoplysninger gemt", "success")
        return RedirectResponse("/admin/settings", status_code=303)

    if planning_notice_days_value < 0:
        flash(request, "Varslingsperiode skal være 0 eller højere", "error")
        return RedirectResponse("/admin/settings", status_code=303)

    set_setting_value(db, "planning_notice_days", str(planning_notice_days_value))
    db.commit()
    flash(request, "Indstillinger gemt", "success")
    return RedirectResponse("/admin/settings", status_code=303)
