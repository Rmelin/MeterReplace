from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app import models

PLANNING_NOTICE_DAYS_KEY = "planning_notice_days"
DEFAULT_PLANNING_NOTICE_DAYS = 14


def get_setting_value(db: Session, key: str) -> str | None:
    entry = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    return entry.value if entry else None


def set_setting_value(db: Session, key: str, value: str) -> None:
    entry = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    if entry:
        entry.value = value
        return
    db.add(models.AppSetting(key=key, value=value))


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
