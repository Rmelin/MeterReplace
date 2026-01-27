from __future__ import annotations

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def authenticate_user(db: Session, username: str, password: str) -> models.User | None:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def login_user(session: dict, user: models.User) -> None:
    session["user_id"] = user.id


def logout_user(session: dict) -> None:
    session.pop("user_id", None)
