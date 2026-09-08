from __future__ import annotations

import logging

from app.db import SessionLocal
from app.push_notifications import process_pending_deliveries, push_is_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    if not push_is_configured():
        logger.error("Web Push er ikke konfigureret med et gyldigt VAPID-nøglepar")
        raise SystemExit(1)
    with SessionLocal() as db:
        result = process_pending_deliveries(db)
    logger.info(
        "Push-leveringer: sent=%s retried=%s failed=%s",
        result["sent"],
        result["retried"],
        result["failed"],
    )


if __name__ == "__main__":
    main()
