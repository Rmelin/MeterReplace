from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app import models


def flash(request: Request, message: str, category: str = "info") -> None:
    flashes = request.session.setdefault("_flashes", [])
    flashes.append({"message": message, "category": category})


def consume_flashes(request: Request) -> list[dict[str, str]]:
    return request.session.pop("_flashes", [])


def get_optional_user(request: Request, db: Session) -> models.User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> models.User:
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_role(*roles: models.UserRole) -> Callable:
    def _require_role(
        request: Request, db: Session = Depends(get_db)
    ) -> models.User:
        user = get_current_user(request, db)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Access denied")
        return user

    return _require_role
