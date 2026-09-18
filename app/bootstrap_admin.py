"""Explicit first administrator setup: python -m app.bootstrap_admin."""

from getpass import getpass

from app import models
from app.auth import hash_password
from app.db import SessionLocal


def create_admin(db, username: str, password: str) -> None:
    if db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).first():
        raise ValueError(
            "Der findes allerede en administrator; brug brugeradministrationen"
        )
    username = username.strip()
    if not username or len(username) > 120:
        raise ValueError("Brugernavn skal være mellem 1 og 120 tegn")
    if len(password) < 16 or password == "admin123":
        raise ValueError("Adgangskoden skal være mindst 16 tegn")
    if db.query(models.User).filter(models.User.username == username).first():
        raise ValueError("Brugernavnet findes allerede")
    db.add(
        models.User(
            username=username,
            role=models.UserRole.ADMIN,
            password_hash=hash_password(password),
        )
    )
    db.commit()


def main():
    username = input("Administratorens brugernavn: ")
    password = getpass("Adgangskode (mindst 16 tegn): ")
    if password != getpass("Gentag adgangskoden: "):
        raise SystemExit("Adgangskoderne er ikke ens")
    try:
        with SessionLocal() as db:
            create_admin(db, username, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Administrator oprettet")


if __name__ == "__main__":
    main()
