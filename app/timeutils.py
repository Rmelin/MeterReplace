from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naiv UTC-tid, samme semantik som det udgåede datetime.utcnow().

    Databasen gemmer naive UTC-tider, så vi fjerner tzinfo bevidst for at
    kunne sammenligne direkte med værdier fra SQLAlchemy.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
