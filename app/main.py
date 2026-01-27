from __future__ import annotations

from datetime import datetime
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from app import models
from app.db import SessionLocal, init_db
from app.dependencies import consume_flashes, get_optional_user
from app.routes import admin_addresses, admin_appointments, admin_availability, admin_completed_import, admin_inventory, admin_letters, admin_missing_photos, admin_planning, admin_status, admin_street_priority, admin_users, auth, resident, user_dashboard, vvs_availability, vvs_tasks

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    session_cookie="vand_session",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/upload", StaticFiles(directory="data/uploads"), name="uploads")

app.state.templates = None


@app.on_event("startup")
def startup() -> None:
    init_db()
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["year"] = datetime.utcnow().year
    app.state.templates = templates


app.include_router(auth.router)
app.include_router(admin_addresses.router)
app.include_router(admin_inventory.router)
app.include_router(admin_users.router)
app.include_router(admin_availability.router)
app.include_router(admin_planning.router)
app.include_router(admin_appointments.router)
app.include_router(admin_completed_import.router)
app.include_router(admin_letters.router)
app.include_router(admin_missing_photos.router)
app.include_router(admin_status.router)
app.include_router(admin_street_priority.router)
app.include_router(user_dashboard.router)
app.include_router(resident.router)
app.include_router(vvs_tasks.router)
app.include_router(vvs_availability.router)


@app.get("/")
def index(request: Request):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == models.UserRole.ADMIN:
        return RedirectResponse("/admin/addresses", status_code=303)
    if user.role == models.UserRole.USER:
        return RedirectResponse("/user/dashboard", status_code=303)
    return RedirectResponse("/vvs", status_code=303)


@app.exception_handler(403)
def access_denied(request: Request, exc):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    return request.app.state.templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_code": 403,
            "message": "Adgang nægtet",
        },
        status_code=403,
    )


@app.exception_handler(404)
def not_found(request: Request, exc):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    return request.app.state.templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_code": 404,
            "message": "Siden findes ikke",
        },
        status_code=404,
    )


@app.exception_handler(500)
def server_error(request: Request, exc):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    return request.app.state.templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_code": 500,
            "message": "Der opstod en uventet fejl",
        },
        status_code=500,
    )
