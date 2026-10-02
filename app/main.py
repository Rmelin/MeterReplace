from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, RedirectResponse

from app import models
from app.app_settings import support_contact
from app.db import SessionLocal, init_db
from app.dependencies import consume_flashes, get_optional_user
from app.routes import admin_addresses, admin_appointments, admin_availability, admin_completed_import, admin_inventory, admin_letters, admin_messages, admin_missing_photos, admin_planning, admin_register_import, admin_settings, admin_status, admin_street_priority, admin_users, auth, push, resident, user_dashboard, vvs_availability, vvs_tasks
from app.timeutils import utc_now

from app.security import RateLimiter, SecurityMiddleware, security_settings
from app.routes import uploads


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["year"] = utc_now().year
    app.state.templates = templates
    yield


settings = security_settings()
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SecurityMiddleware,
    limiter=RateLimiter(Path("data/security/rate-limits.db"), settings.secret_key),
    production=settings.production,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="vand_session",
    https_only=settings.secure_cookie,
    same_site="lax",
)
if settings.allowed_host:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[settings.allowed_host])

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(uploads.router)

app.include_router(auth.router)
app.include_router(admin_addresses.router)
app.include_router(admin_inventory.router)
app.include_router(admin_users.router)
app.include_router(admin_availability.router)
app.include_router(admin_planning.router)
app.include_router(admin_appointments.router)
app.include_router(admin_completed_import.router)
app.include_router(admin_register_import.router)
app.include_router(admin_letters.router)
app.include_router(admin_messages.router)
app.include_router(admin_missing_photos.router)
app.include_router(admin_status.router)
app.include_router(admin_settings.router)
app.include_router(admin_street_priority.router)
app.include_router(user_dashboard.router)
app.include_router(push.router)
app.include_router(resident.router)
app.include_router(vvs_tasks.router)
app.include_router(vvs_availability.router)


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(
        Path("app/static/service-worker.js"),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/",
        },
    )


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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    return RedirectResponse("/static/favicon.ico")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon() -> RedirectResponse:
    return RedirectResponse("/static/icon-180.png")


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon_precomposed() -> RedirectResponse:
    return RedirectResponse("/static/icon-180.png")


@app.exception_handler(403)
def access_denied(request: Request, exc):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    return request.app.state.templates.TemplateResponse(
        request, "error.html",
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
    is_resident_404 = request.url.path == "/r" or request.url.path.startswith("/r/")
    with SessionLocal() as db:
        user = get_optional_user(request, db)
        contact = support_contact(db) if is_resident_404 else None
    return request.app.state.templates.TemplateResponse(
        request, "error.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_code": 404,
            "message": (
                "Beboerlinket kunne ikke findes eller er ikke længere gyldigt."
                if is_resident_404
                else "Siden findes ikke"
            ),
            "is_resident_404": is_resident_404,
            "support_contact": contact,
        },
        status_code=404,
        headers=(
            {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
            if is_resident_404
            else None
        ),
    )


@app.exception_handler(500)
def server_error(request: Request, exc):
    with SessionLocal() as db:
        user = get_optional_user(request, db)
    return request.app.state.templates.TemplateResponse(
        request, "error.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_code": 500,
            "message": "Der opstod en uventet fejl",
        },
        status_code=500,
    )
