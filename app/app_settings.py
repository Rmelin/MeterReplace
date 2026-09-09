from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re

from sqlalchemy.orm import Session

from app import models

PLANNING_NOTICE_DAYS_KEY = "planning_notice_days"
DEFAULT_PLANNING_NOTICE_DAYS = 14
SUPPORT_EMAIL_KEY = "support_email"
SUPPORT_PHONE_KEY = "support_phone"
SUPPORT_PHONE_HOURS_KEY = "support_phone_hours"


@dataclass(frozen=True)
class SupportContact:
    email: str
    phone: str
    phone_hours: str
    phone_href: str


def get_setting_value(db: Session, key: str) -> str | None:
    entry = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    return entry.value if entry else None


def set_setting_value(db: Session, key: str, value: str) -> None:
    entry = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    if entry:
        entry.value = value
        return
    db.add(models.AppSetting(key=key, value=value))


def support_contact(db: Session) -> SupportContact:
    email = (get_setting_value(db, SUPPORT_EMAIL_KEY) or "").strip()
    phone = (get_setting_value(db, SUPPORT_PHONE_KEY) or "").strip()
    phone_hours = (get_setting_value(db, SUPPORT_PHONE_HOURS_KEY) or "").strip()
    phone_href = re.sub(r"[^0-9+]", "", phone)
    if phone_href.count("+") > 1 or ("+" in phone_href and not phone_href.startswith("+")):
        phone_href = ""
    return SupportContact(email, phone, phone_hours, phone_href)


def planning_notice_days(db: Session) -> int:
    raw = get_setting_value(db, PLANNING_NOTICE_DAYS_KEY)
    if raw is None:
        return DEFAULT_PLANNING_NOTICE_DAYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PLANNING_NOTICE_DAYS
    return max(value, 0)


def is_within_planning_notice(plan_date: date, notice_days: int) -> bool:
    cutoff = date.today() + timedelta(days=max(notice_days, 0))
    return plan_date < cutoff
