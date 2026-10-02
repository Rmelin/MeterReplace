from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def copenhagen_today() -> date:
    return datetime.now(ZoneInfo("Europe/Copenhagen")).date()


def utc_now() -> datetime:
    """Naiv UTC-tid, samme semantik som det udgåede datetime.utcnow().

    Databasen gemmer naive UTC-tider, så vi fjerner tzinfo bevidst for at
    kunne sammenligne direkte med værdier fra SQLAlchemy.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
