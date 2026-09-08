from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import require_role
from app.push_notifications import push_is_configured, vapid_public_key

router = APIRouter(prefix="/api/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionPayload(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)
    expirationTime: float | None = None
    keys: PushKeys


class PushUnsubscribePayload(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


def validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise HTTPException(status_code=400, detail="Ugyldigt push-endpoint")
    if hostname != "push.apple.com" and not hostname.endswith(".push.apple.com"):
        raise HTTPException(status_code=400, detail="Push-endpointet er ikke fra Apple")
    return endpoint


def expiration_datetime(value: float | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.utcfromtimestamp(value / 1000)
    except (OverflowError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Ugyldig udløbstid") from None


@router.get("/config")
def push_config(
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    del user
    return {
        "configured": push_is_configured(),
        "publicKey": vapid_public_key(),
    }


@router.post("/subscriptions", status_code=201)
def subscribe(
    payload: PushSubscriptionPayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    if not push_is_configured():
        raise HTTPException(status_code=503, detail="Web Push er ikke konfigureret")

    endpoint = validate_endpoint(payload.endpoint)
    subscription = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.endpoint == endpoint)
        .first()
    )
    now = datetime.utcnow()
    if subscription:
        subscription.user_id = user.id
        subscription.p256dh = payload.keys.p256dh
        subscription.auth = payload.keys.auth
        subscription.expiration_time = expiration_datetime(payload.expirationTime)
        subscription.updated_at = now
        subscription.disabled_at = None
        subscription.failure_count = 0
        subscription.last_error = None
    else:
        subscription = models.PushSubscription(
            user_id=user.id,
            endpoint=endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            expiration_time=expiration_datetime(payload.expirationTime),
            created_at=now,
            updated_at=now,
            failure_count=0,
        )
        db.add(subscription)
    db.commit()
    return {"subscribed": True}


@router.delete("/subscriptions")
def unsubscribe(
    payload: PushUnsubscribePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    endpoint = validate_endpoint(payload.endpoint)
    subscription = (
        db.query(models.PushSubscription)
        .filter(
            models.PushSubscription.endpoint == endpoint,
            models.PushSubscription.user_id == user.id,
        )
        .first()
    )
    if subscription and subscription.disabled_at is None:
        now = datetime.utcnow()
        subscription.disabled_at = now
        db.query(models.PushDelivery).filter(
            models.PushDelivery.subscription_id == subscription.id,
            models.PushDelivery.sent_at.is_(None),
            models.PushDelivery.failed_at.is_(None),
        ).update(
            {
                "failed_at": now,
                "last_error": "Abonnementet er deaktiveret",
                "locked_until": None,
            },
            synchronize_session=False,
        )
        db.commit()
    return {"subscribed": False}
