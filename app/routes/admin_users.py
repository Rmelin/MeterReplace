from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import auth, models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/users", tags=["admin"])


def fetch_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def parse_role(value: str) -> models.UserRole | None:
    value = value.strip().lower()
    for role in models.UserRole:
        if role.value == value:
            return role
    return None


@router.get("")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    users = db.query(models.User).order_by(models.User.username).all()
    return request.app.state.templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "users": users,
            "roles": [role.value for role in models.UserRole],
        },
    )


@router.post("")
def create_user(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    username = username.strip().lower()
    role_value = parse_role(role)
    if not username or not password:
        flash(request, "Brugernavn og adgangskode er påkrævet", "error")
        return RedirectResponse("/admin/users", status_code=303)

    if not role_value:
        flash(request, "Vælg en gyldig rolle", "error")
        return RedirectResponse("/admin/users", status_code=303)

    if db.query(models.User).filter(models.User.username == username).first():
        flash(request, "Brugernavn findes allerede", "error")
        return RedirectResponse("/admin/users", status_code=303)

    db.add(
        models.User(
            username=username,
            role=role_value,
            password_hash=auth.hash_password(password),
        )
    )
    db.commit()

    flash(request, "Bruger oprettet", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/{user_id}/edit")
def edit_user_form(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    target_user = fetch_user(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    return request.app.state.templates.TemplateResponse(
        "admin_user_edit.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "target_user": target_user,
            "roles": [role.value for role in models.UserRole],
        },
    )


@router.post("/{user_id}/edit")
def update_user(
    request: Request,
    user_id: int,
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    target_user = fetch_user(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")

    username = username.strip().lower()
    if not username:
        flash(request, "Brugernavn er påkrævet", "error")
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=303)

    role_value = parse_role(role)
    if not role_value:
        flash(request, "Vælg en gyldig rolle", "error")
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=303)

    existing = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.id != user_id)
        .first()
    )
    if existing:
        flash(request, "Brugernavn findes allerede", "error")
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=303)

    target_user.username = username
    target_user.role = role_value
    if password:
        target_user.password_hash = auth.hash_password(password)

    db.commit()
    flash(request, "Bruger opdateret", "success")
    return RedirectResponse("/admin/users", status_code=303)
