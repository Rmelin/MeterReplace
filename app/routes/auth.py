from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import auth, models
from app.db import get_db
from app.dependencies import consume_flashes, flash, get_current_user

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "flashes": consume_flashes(request),
            "current_user": None,
        },
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = auth.authenticate_user(db, username.strip(), password)
    if not user:
        flash(request, "Forkert brugernavn eller adgangskode", "error")
        return RedirectResponse("/login", status_code=303)

    auth.login_user(request.session, user)
    flash(request, "Velkommen tilbage", "success")
    if user.role == models.UserRole.ADMIN:
        return RedirectResponse("/admin/addresses", status_code=303)
    if user.role == models.UserRole.USER:
        return RedirectResponse("/user/dashboard", status_code=303)
    return RedirectResponse("/vvs/tasks", status_code=303)


@router.post("/logout")
def logout(request: Request, user=Depends(get_current_user)):
    auth.logout_user(request.session)
    flash(request, "Du er logget ud", "success")
    return RedirectResponse("/login", status_code=303)
