"""Private uploads are served only after checking the corresponding database row."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from app import models
from app.db import get_db
from app.dependencies import get_current_user

router = APIRouter()
UPLOAD_DIR = Path("data/uploads")


@router.get("/upload/{file_path:path}")
def download_upload(
    file_path: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if "\\" in file_path or ":" in file_path or Path(file_path).is_absolute():
        raise HTTPException(404)
    root = UPLOAD_DIR.resolve()
    path = (root / file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404)
    photos = db.query(models.AppointmentPhoto).filter(
        models.AppointmentPhoto.file_path == file_path
    )
    if user.role in {models.UserRole.ADMIN, models.UserRole.USER}:
        allowed = (
            photos.first() is not None
            or db.query(models.LetterTemplate)
            .filter(models.LetterTemplate.logo_path == file_path)
            .first()
            is not None
        )
    elif user.role == models.UserRole.VVS:
        allowed = (
            photos.join(models.Appointment)
            .filter(models.Appointment.contractor_id == user.id)
            .first()
            is not None
        )
    else:
        allowed = False
    if not allowed:
        raise HTTPException(404)
    # Legacy active content must never execute under the application's origin.
    image_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = image_types.get(path.suffix.lower())
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
        content_disposition_type="inline" if media_type else "attachment",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
