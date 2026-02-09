from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import re
import unicodedata
from uuid import uuid4
import base64
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from markdown import markdown
import qrcode
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response
from weasyprint import HTML

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/letters", tags=["admin"])

UPLOAD_DIR = Path("data") / "uploads" / "logo"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BODY = (
    "# Kære beboer\n\n"
    "Vi kommer og udskifter vandmåleren på den planlagte dato. "
    "VVS har adgang i det angivne tidsrum.\n\n"
    "## Med venlig hilsen\nDit vandværk"
)


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text) or "logo"


def save_logo(file: UploadFile) -> str:
    extension = Path(file.filename or "").suffix.lower() or ".png"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(Path(file.filename or "logo").stem)
    counter = 1
    while True:
        filename = f"{slug}-{timestamp}-{counter}{extension}"
        path = UPLOAD_DIR / filename
        if not path.exists():
            break
        counter += 1
    with path.open("wb") as buffer:
        buffer.write(file.file.read())
    return str(path.relative_to(Path("data") / "uploads"))


def ensure_image(file: UploadFile) -> bool:
    return file.content_type is not None and file.content_type.startswith("image/")


def latest_template(db: Session) -> models.LetterTemplate | None:
    return db.query(models.LetterTemplate).order_by(models.LetterTemplate.updated_at.desc()).first()


def render_body(body_markdown: str) -> str:
    return markdown(body_markdown, extensions=["extra", "nl2br"])


def time_window(starts_at: datetime) -> str:
    return "Formiddag (08:00–12:00)" if starts_at.hour < 12 else "Eftermiddag (12:00–16:00)"


def public_base_url(request: Request) -> str:
    configured = os.environ.get("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def appointment_for_address(db: Session, address_id: int) -> models.Appointment | None:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id == address_id,
            models.Appointment.status.in_(
                [models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.INFORMED]
            ),
        )
        .order_by(models.Appointment.starts_at.desc())
        .first()
    )


def logo_paths(template: models.LetterTemplate | None) -> tuple[str | None, str | None]:
    if not template or not template.logo_path:
        return None, None
    relative_path = template.logo_path
    file_path = (Path("data") / "uploads" / relative_path).resolve()
    return f"/upload/{relative_path}", file_path.as_uri()


def get_or_create_link(db: Session, address: models.Address) -> models.ResidentLink:
    link = (
        db.query(models.ResidentLink)
        .filter(
            models.ResidentLink.address_id == address.id,
            models.ResidentLink.active.is_(True),
        )
        .order_by(models.ResidentLink.created_at.desc())
        .first()
    )
    if link:
        return link
    token = uuid4().hex
    link = models.ResidentLink(address_id=address.id, token=token, active=True)
    db.add(link)
    db.commit()
    return link


def response_label(response_type: str) -> str:
    labels = {
        "reschedule_request": "Tidspunkt passer ikke",
        "buffer_note": "Målerbrønd angivet",
        "confirm_time": "Tidspunkt bekræftet",
    }
    return labels.get(response_type, "Svar modtaget")


def qr_image(url: str) -> str:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def letter_context(
    address: models.Address,
    appointment: models.Appointment,
    template: models.LetterTemplate,
    base_url: str,
    db: Session,
):
    logo_url, logo_file = logo_paths(template)
    include_resident_link = (
        template.include_resident_link if template.include_resident_link is not None else True
    )
    response_url = None
    qr_data = None
    link_active = None
    if include_resident_link:
        link = get_or_create_link(db, address)
        response_url = f"{base_url}/r/{link.token}"
        qr_data = qr_image(response_url)
        link_active = link.active
    return {
        "address": address,
        "appointment": appointment,
        "body_html": render_body(template.body_markdown),
        "logo_url": logo_url,
        "logo_file": logo_file,
        "visit_date": appointment.starts_at.strftime("%d/%m/%Y"),
        "visit_window": time_window(appointment.starts_at),
        "include_resident_link": include_resident_link,
        "response_url": response_url,
        "qr_data": qr_data,
        "link_active": link_active,
    }


def render_pdf(html: str) -> bytes:
    base_url = str(Path(".").resolve())
    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
    return pdf_bytes if pdf_bytes is not None else b""


def planned_dates(db: Session) -> list[str]:
    rows = (
        db.query(func.date(models.Appointment.starts_at))
        .filter(
            models.Appointment.status.in_(
                [models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.INFORMED]
            )
        )
        .distinct()
        .order_by(func.date(models.Appointment.starts_at))
        .all()
    )
    values: list[str] = []
    for (value,) in rows:
        if value is None:
            continue
        if isinstance(value, str):
            values.append(value)
        else:
            values.append(value.isoformat())
    return values


@router.get("/template")
def template_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    template = latest_template(db)
    if not template:
        template = models.LetterTemplate(
            body_markdown=DEFAULT_BODY,
            include_resident_link=True,
        )
    logo_url, _ = logo_paths(template)
    return request.app.state.templates.TemplateResponse(
        "admin_letter_template.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "template": template,
            "logo_url": logo_url,
            "planned_dates": planned_dates(db),
        },
    )


@router.post("/template")
def update_template(
    request: Request,
    body_markdown: str = Form(""),
    include_resident_link: bool = Form(False),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    body = body_markdown.strip()
    if not body:
        flash(request, "Teksten må ikke være tom", "error")
        return RedirectResponse("/admin/letters/template", status_code=303)

    template = latest_template(db)
    logo_path = template.logo_path if template else None

    if logo and logo.filename:
        if not ensure_image(logo):
            flash(request, "Logo skal være et billede", "error")
            return RedirectResponse("/admin/letters/template", status_code=303)
        logo_path = save_logo(logo)

    if template:
        template.body_markdown = body
        template.logo_path = logo_path
        template.include_resident_link = include_resident_link
        template.updated_at = datetime.utcnow()
    else:
        db.add(
            models.LetterTemplate(
                body_markdown=body,
                logo_path=logo_path,
                include_resident_link=include_resident_link,
                updated_at=datetime.utcnow(),
            )
        )

    db.commit()
    flash(request, "Skabelon opdateret", "success")
    return RedirectResponse("/admin/letters/template", status_code=303)


@router.get("/address/{address_id}")
def letter_preview(
    request: Request,
    address_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    appointment = appointment_for_address(db, address_id)
    if not appointment:
        flash(request, "Adresse er ikke planlagt", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    template = latest_template(db) or models.LetterTemplate(body_markdown=DEFAULT_BODY, include_resident_link=True)
    base_url = public_base_url(request)
    context = letter_context(address, appointment, template, base_url, db)
    latest_response = (
        db.query(models.ResidentResponse)
        .filter(models.ResidentResponse.address_id == address.id)
        .order_by(models.ResidentResponse.created_at.desc())
        .first()
    )
    response_meta = None
    if latest_response:
        response_meta = {
            "label": response_label(latest_response.response_type),
            "date": latest_response.created_at.strftime("%d/%m/%Y"),
        }

    return request.app.state.templates.TemplateResponse(
        "admin_letter_preview.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "resident_response": response_meta,
            **context,
        },
    )


@router.get("/address/{address_id}/pdf")
def letter_pdf(
    request: Request,
    address_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    appointment = appointment_for_address(db, address_id)
    if not appointment:
        flash(request, "Adresse er ikke planlagt", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    template = latest_template(db) or models.LetterTemplate(body_markdown=DEFAULT_BODY, include_resident_link=True)
    base_url = public_base_url(request)
    context = letter_context(address, appointment, template, base_url, db)

    html = request.app.state.templates.get_template("letter_pdf.html").render(
        letters=[context]
    )
    pdf_bytes = render_pdf(html)

    if appointment.status != models.AppointmentStatus.INFORMED:
        appointment.status = models.AppointmentStatus.INFORMED
        appointment.changed_date = datetime.utcnow()
        appointment.changed_by_user_id = user.id
        db.commit()

    filename = f"brev-{address.street}-{address.house_no}.pdf"
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/batch/pdf")
def batch_pdf(
    request: Request,
    date: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    planned = planned_dates(db)
    if date not in planned:
        flash(request, "Vælg en planlagt dato", "error")
        return RedirectResponse("/admin/letters/template", status_code=303)

    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        flash(request, "Dato er ugyldig", "error")
        return RedirectResponse("/admin/letters/template", status_code=303)

    rows = (
        db.query(models.Appointment, models.Address)
        .join(models.Address, models.Address.id == models.Appointment.address_id)
        .filter(
            models.Appointment.status.in_(
                [models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.INFORMED]
            ),
            func.date(models.Appointment.starts_at) == day,
        )
        .order_by(models.Appointment.starts_at)
        .all()
    )

    if not rows:
        flash(request, "Ingen planlagte adresser på datoen", "error")
        return RedirectResponse("/admin/letters/template", status_code=303)

    template = latest_template(db) or models.LetterTemplate(body_markdown=DEFAULT_BODY, include_resident_link=True)
    base_url = public_base_url(request)
    letters = [
        letter_context(address, appointment, template, base_url, db)
        for appointment, address in rows
    ]

    html = request.app.state.templates.get_template("letter_pdf.html").render(
        letters=letters
    )

    pdf_bytes = render_pdf(html)

    appointments_to_update = [appointment for appointment, _ in rows]
    updated = False
    for appointment in appointments_to_update:
        if appointment.status != models.AppointmentStatus.INFORMED:
            appointment.status = models.AppointmentStatus.INFORMED
            appointment.changed_date = datetime.utcnow()
            appointment.changed_by_user_id = user.id
            updated = True
    if updated:
        db.commit()

    filename = f"breve-{day.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
