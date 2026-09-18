from __future__ import annotations

import base64
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app import models
from app.timeutils import utc_now

MAX_ATTEMPTS = 5
RETRY_DELAYS = (1, 5, 30, 120)


def vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def push_is_configured() -> bool:
    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not private_key or not (
        subject.startswith("mailto:") or subject.startswith("https://")
    ):
        return False
    try:
        key = serialization.load_pem_private_key(Path(private_key).read_bytes(), None)
    except (OSError, TypeError, ValueError):
        return False
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        return False
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    derived_public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    return derived_public_key == vapid_public_key().rstrip("=")


def enqueue_message_pushes(
    db: Session,
    response: models.ResidentResponse,
) -> int:
    if response.mailbox_status != models.ResidentMessageStatus.NEW:
        return 0

    db.flush()
    subscription_ids = [
        row[0]
        for row in db.query(models.PushSubscription.id)
        .join(models.User, models.User.id == models.PushSubscription.user_id)
        .filter(
            models.User.role == models.UserRole.ADMIN,
            models.PushSubscription.disabled_at.is_(None),
        )
        .all()
    ]
    now = utc_now()
    for subscription_id in subscription_ids:
        db.add(
            models.PushDelivery(
                resident_response_id=response.id,
                subscription_id=subscription_id,
                attempts=0,
                created_at=now,
                next_attempt_at=now,
            )
        )
    return len(subscription_ids)


def send_push(subscription: models.PushSubscription, response_id: int) -> None:
    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not push_is_configured():
        raise RuntimeError("Web Push er ikke konfigureret")

    payload = json.dumps(
        {
            "title": "Ny beboerbesked",
            "body": "Der er kommet en ny besked",
            "url": "/admin/messages?folder=new",
            "tag": f"resident-message-{response_id}",
        }
    )
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=payload,
        vapid_private_key=private_key,
        vapid_claims={"sub": subject},
        ttl=3600,
        timeout=10,
    )


def _retry_at(exc: WebPushException, now: datetime) -> datetime | None:
    value = getattr(exc, "retry_after", None)
    if isinstance(value, (int, float)):
        return now + timedelta(seconds=max(0, min(value, 86400)))
    if isinstance(value, str):
        if value.isdigit():
            return now + timedelta(seconds=min(int(value), 86400))
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = max(0, min((parsed.timestamp() - now.timestamp()), 86400))
        return now + timedelta(seconds=seconds)
    return None


def _is_apple_idle_timeout(exc: WebPushException) -> bool:
    if exc.response is None:
        return False
    try:
        body = exc.response.json()
    except (TypeError, ValueError):
        return False
    return isinstance(body, dict) and body.get("reason") == "IdleTimeout"


def _retry_delivery(
    delivery: models.PushDelivery,
    now: datetime,
    retry_at: datetime | None = None,
) -> None:
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.failed_at = now
        return
    if retry_at is not None:
        delivery.next_attempt_at = retry_at
        return
    delay_index = min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)
    delivery.next_attempt_at = now + timedelta(minutes=RETRY_DELAYS[delay_index])


def process_pending_deliveries(
    db: Session,
    limit: int = 50,
    sender: Callable[[models.PushSubscription, int], None] = send_push,
) -> dict[str, int]:
    now = utc_now()
    delivery_ids = [
        row[0]
        for row in db.query(models.PushDelivery.id)
        .filter(
            models.PushDelivery.sent_at.is_(None),
            models.PushDelivery.failed_at.is_(None),
            models.PushDelivery.next_attempt_at <= now,
            (
                models.PushDelivery.locked_until.is_(None)
                | (models.PushDelivery.locked_until < now)
            ),
        )
        .order_by(models.PushDelivery.next_attempt_at, models.PushDelivery.id)
        .limit(max(1, min(limit, 500)))
        .all()
    ]
    if not delivery_ids:
        return {"sent": 0, "retried": 0, "failed": 0}

    result = {"sent": 0, "retried": 0, "failed": 0}
    for delivery_id in delivery_ids:
        claim_time = utc_now()
        claimed = (
            db.query(models.PushDelivery)
            .filter(
                models.PushDelivery.id == delivery_id,
                models.PushDelivery.sent_at.is_(None),
                models.PushDelivery.failed_at.is_(None),
                models.PushDelivery.next_attempt_at <= claim_time,
                (
                    models.PushDelivery.locked_until.is_(None)
                    | (models.PushDelivery.locked_until < claim_time)
                ),
            )
            .update(
                {"locked_until": claim_time + timedelta(minutes=1)},
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed != 1:
            continue

        delivery = db.get(models.PushDelivery, delivery_id)
        if not delivery or delivery.sent_at or delivery.failed_at:
            continue
        subscription = db.get(models.PushSubscription, delivery.subscription_id)
        attempt_time = utc_now()
        delivery.attempts += 1
        delivery.locked_until = None

        if not subscription or subscription.disabled_at:
            delivery.failed_at = attempt_time
            delivery.last_error = "Abonnementet er deaktiveret"
            result["failed"] += 1
            db.commit()
            continue

        try:
            sender(subscription, delivery.resident_response_id)
        except WebPushException as exc:
            status_code = getattr(exc, "status_code", None)
            delivery.last_error = (
                f"Push-tjenesten svarede HTTP {status_code}"
                if status_code
                else "Push-tjenesten kunne ikke kontaktes"
            )
            subscription.failure_count += 1
            subscription.last_error = delivery.last_error
            if status_code in {404, 410}:
                subscription.disabled_at = attempt_time
                delivery.failed_at = attempt_time
                result["failed"] += 1
            elif (
                status_code is None
                or status_code in {401, 403, 408, 425, 429}
                or status_code >= 500
                or _is_apple_idle_timeout(exc)
            ):
                retry_at = _retry_at(exc, attempt_time) if status_code == 429 else None
                _retry_delivery(delivery, attempt_time, retry_at)
                result["failed" if delivery.failed_at else "retried"] += 1
            else:
                delivery.failed_at = attempt_time
                result["failed"] += 1
        except Exception:
            delivery.last_error = "Midlertidig fejl ved afsendelse"
            subscription.failure_count += 1
            subscription.last_error = delivery.last_error
            _retry_delivery(delivery, attempt_time)
            result["failed" if delivery.failed_at else "retried"] += 1
        else:
            delivery.sent_at = attempt_time
            delivery.last_error = None
            subscription.last_success_at = attempt_time
            subscription.failure_count = 0
            subscription.last_error = None
            result["sent"] += 1
        db.commit()
    return result
