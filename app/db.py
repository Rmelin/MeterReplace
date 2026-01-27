from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR / 'app.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models
    from app.auth import hash_password

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.query(models.User).first():
            admin = models.User(
                username="admin",
                role=models.UserRole.ADMIN,
                password_hash=hash_password("admin123"),
            )
            db.add(admin)
            db.commit()
