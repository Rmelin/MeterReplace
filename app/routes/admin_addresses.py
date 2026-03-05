from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

PHOTO_LABELS = {
    "both": "Begge målere",
    "new": "Ny måler",
    "old": "Gammel måler",
}

RESPONSE_LABELS = {
    "reschedule_request": "Tidspunkt passer ikke",
    "buffer_note": "Målerbrønd angivet",
    "confirm_time": "Tidspunkt bekræftet",
}

router = APIRouter(prefix="/admin/addresses", tags=["admin"])


class CoordinatePayload(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


STATUS_FILTERS = [
    {"value": "all", "label": "Alle"},
    {"value": "planned", "label": "Planlagt"},
    {"value": "informed", "label": "Beboer/kunde informeret"},
    {"value": "completed", "label": "Skiftet"},
    {"value": "closed", "label": "Afsluttet"},
    {"value": "not_home", "label": "Ikke hjemme (nuværende)"},
    {"value": "not_home_history", "label": "Ikke hjemme (historik)"},
    {"value": "needs_reschedule", "label": "Behov for ny dato"},
    {"value": "unplanned", "label": "Ikke planlagt"},
]


def geocode_query(query: str) -> tuple[float, float] | None:
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MeterReplace/1.0 (admin dashboard)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
    except Exception:
        return None

    try:
        data = json.loads(payload)
    except Exception:
        return None

    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def geocode_address(
    street: str, house_no: str, zip_code: str, city: str
) -> tuple[float, float] | None:
    query = f"{street} {house_no}, {zip_code} {city}, Denmark"
    return geocode_query(query)


def latest_status_map(
    db: Session, address_ids: list[int]
) -> dict[int, models.AppointmentStatus]:
    if not address_ids:
        return {}
    appointments = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id.in_(address_ids),
            models.Appointment.status.in_(
                [
                    models.AppointmentStatus.SCHEDULED,
                    models.AppointmentStatus.INFORMED,
                    models.AppointmentStatus.COMPLETED,
                    models.AppointmentStatus.CLOSED,
                    models.AppointmentStatus.NOT_HOME,
                    models.AppointmentStatus.NEEDS_RESCHEDULE,
                ]
            ),
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )
    status_map: dict[int, models.AppointmentStatus] = {}
    for appointment in appointments:
        if appointment.address_id in status_map:
            continue
        status_map[appointment.address_id] = appointment.status
    return status_map


def street_priority_map(db: Session) -> dict[str, int]:
    rows = db.query(models.StreetPriority).all()
    return {row.street.lower(): row.priority for row in rows}


def address_sort_key(
    address: models.Address, priority_map: dict[str, int]
) -> tuple[int, str, int, str]:
    street = (address.street or "").lower()
    priority = priority_map.get(street, 0)
    house_no = (address.house_no or "").strip()
    match = re.match(r"(\d+)\s*(.*)", house_no)
    if match:
        number = int(match.group(1))
        suffix = match.group(2).strip().lower()
        return (-priority, street, number, suffix)
    return (-priority, street, 999999, house_no.lower())


def parse_datetime_local(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def format_status_date(value: datetime, current_year: int) -> str:
    if value.year != current_year:
        return value.strftime("%d/%m/%Y")
    return value.strftime("%d/%m")


def status_label_and_key(
    appointment: models.Appointment | None, current_year: int
) -> tuple[str, str]:
    if not appointment:
        return "Ikke planlagt", "unplanned"
    status = appointment.status
    status_date = format_status_date(appointment.starts_at, current_year)
    if status == models.AppointmentStatus.COMPLETED:
        return "Skiftet " + status_date, "completed"
    if status == models.AppointmentStatus.CLOSED:
        return "Afsluttet " + status_date, "closed"
    if status == models.AppointmentStatus.INFORMED:
        return "Informeret, planlagt til den " + status_date, "informed"
    if status == models.AppointmentStatus.NOT_HOME:
        return "Ikke hjemme", "not_home"
    if status == models.AppointmentStatus.NEEDS_RESCHEDULE:
        return "Planlagt til " + status_date + " • Behov for ny dato", "needs_reschedule"
    return "Planlagt " + status_date, "planned"


@router.get("")
def list_addresses(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    query = db.query(models.Address)
    search_value = (q or "").strip().lower()
    if search_value:
        pattern = f"%{search_value}%"
        query = query.filter(
            or_(
                func.lower(models.Address.street).like(pattern),
                func.lower(models.Address.house_no).like(pattern),
                func.lower(models.Address.zip).like(pattern),
                func.lower(models.Address.city).like(pattern),
                func.lower(models.Address.customer_name).like(pattern),
                func.lower(models.Address.customer_email).like(pattern),
                func.lower(models.Address.customer_phone).like(pattern),
            )
        )

    addresses = query.all()
    priority_map = street_priority_map(db)
    addresses = sorted(addresses, key=lambda address: address_sort_key(address, priority_map))
    address_ids = [address.id for address in addresses]
    status_map: dict[int, str] = {}
    status_status_map: dict[int, models.AppointmentStatus] = {}

    allowed_filters = {item["value"] for item in STATUS_FILTERS}
    selected_status = status if status in allowed_filters else "all"

    not_home_history_map: dict[int, int] = {}
    photo_map: dict[int, int] = {}
    resident_response_map: dict[int, dict[str, str]] = {}
    current_year = datetime.utcnow().year
    if address_ids:
        appointments = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.address_id.in_(address_ids),
                models.Appointment.status.in_(
                    [
                        models.AppointmentStatus.SCHEDULED,
                        models.AppointmentStatus.INFORMED,
                        models.AppointmentStatus.COMPLETED,
                        models.AppointmentStatus.CLOSED,
                        models.AppointmentStatus.NOT_HOME,
                        models.AppointmentStatus.NEEDS_RESCHEDULE,
                    ]
                ),
            )
            .order_by(models.Appointment.starts_at.desc())
            .all()
        )
        for appointment in appointments:
            if appointment.address_id in status_map:
                continue
            status_status_map[appointment.address_id] = appointment.status
            status_date = format_status_date(appointment.starts_at, current_year)
            if appointment.status == models.AppointmentStatus.COMPLETED:
                status_map[appointment.address_id] = "Skiftet " + status_date
            elif appointment.status == models.AppointmentStatus.CLOSED:
                status_map[appointment.address_id] = "Afsluttet " + status_date
            elif appointment.status == models.AppointmentStatus.INFORMED:
                status_map[appointment.address_id] = (
                    "Informeret, planlagt til den " + status_date
                )
            elif appointment.status == models.AppointmentStatus.NOT_HOME:
                status_map[appointment.address_id] = "Ikke hjemme"
            elif appointment.status == models.AppointmentStatus.NEEDS_RESCHEDULE:
                status_map[appointment.address_id] = (
                    "Planlagt til " + status_date + " • Behov for ny dato"
                )
            else:
                status_map[appointment.address_id] = "Planlagt " + status_date

        not_home_rows = (
            db.query(models.Appointment.address_id, func.count(models.Appointment.id))
            .filter(
                models.Appointment.address_id.in_(address_ids),
                models.Appointment.status == models.AppointmentStatus.NOT_HOME,
            )
            .group_by(models.Appointment.address_id)
            .all()
        )
        not_home_history_map = {address_id: count for address_id, count in not_home_rows}

        photo_rows = (
            db.query(models.AppointmentPhoto.address_id, func.count(models.AppointmentPhoto.id))
            .filter(models.AppointmentPhoto.address_id.in_(address_ids))
            .group_by(models.AppointmentPhoto.address_id)
            .all()
        )
        photo_map = {address_id: count for address_id, count in photo_rows}

        responses = (
            db.query(models.ResidentResponse)
            .filter(models.ResidentResponse.address_id.in_(address_ids))
            .order_by(models.ResidentResponse.created_at.desc())
            .all()
        )
        for response in responses:
            if response.address_id in resident_response_map:
                continue
            resident_response_map[response.address_id] = {
                "label": RESPONSE_LABELS.get(response.response_type, "Svar modtaget"),
                "date": response.created_at.strftime("%d/%m/%Y"),
            }


    if selected_status != "all":
        filter_map = {
            "planned": {models.AppointmentStatus.SCHEDULED},
            "informed": {models.AppointmentStatus.INFORMED},
            "completed": {models.AppointmentStatus.COMPLETED},
            "closed": {models.AppointmentStatus.CLOSED},
            "not_home": {models.AppointmentStatus.NOT_HOME},
            "needs_reschedule": {models.AppointmentStatus.NEEDS_RESCHEDULE},
        }
        allowed_statuses = filter_map.get(selected_status, set())
        if selected_status == "unplanned":
            addresses = [
                address for address in addresses if address.id not in status_status_map
            ]
        elif selected_status == "not_home_history":
            addresses = [
                address for address in addresses if address.id in not_home_history_map
            ]
        else:
            addresses = [
                address
                for address in addresses
                if status_status_map.get(address.id) in allowed_statuses
            ]

    return request.app.state.templates.TemplateResponse(
        "admin_addresses.html",
        {
            "request": request,
            "addresses": addresses,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_map": status_map,
            "status_status_map": status_status_map,
            "search_query": search_value,
            "status_filters": STATUS_FILTERS,
            "selected_status": selected_status,
            "AppointmentStatus": models.AppointmentStatus,
            "not_home_history_map": not_home_history_map,
            "photo_map": photo_map,
            "resident_response_map": resident_response_map,
        },
    )


@router.post("")
def create_address(
    request: Request,
    street: str = Form(""),
    house_no: str = Form(""),
    zip_code: str = Form("", alias="zip"),
    city: str = Form(""),
    customer_name: str | None = Form(None),
    customer_email: str | None = Form(None),
    customer_phone: str | None = Form(None),
    buffer_flag: bool = Form(False),
    buffer_note: str | None = Form(None),
    blocked_flag: bool = Form(False),
    blocked_note: str | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    street = street.strip()
    house_no = house_no.strip()
    zip_code = zip_code.strip()
    city = city.strip()
    customer_name = (customer_name or "").strip() or None
    customer_email = (customer_email or "").strip() or None
    customer_phone = (customer_phone or "").strip() or None
    buffer_note = (buffer_note or "").strip() or None
    blocked_note = (blocked_note or "").strip() or None
    blocked_reason = blocked_note if blocked_flag else None
    if blocked_flag and not blocked_reason:
        blocked_reason = "Fejl ved stophane"

    if not all([street, house_no, zip_code, city]):
        flash(request, "Alle adressefelter skal udfyldes", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    address = models.Address(
        street=street,
        house_no=house_no,
        zip=zip_code,
        city=city,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        buffer_flag=buffer_flag,
        buffer_note=buffer_note,
        blocked_reason=blocked_reason,
    )
    coords = geocode_address(street, house_no, zip_code, city)
    if coords:
        address.latitude = coords[0]
        address.longitude = coords[1]
    db.add(address)
    db.commit()
    if not coords:
        flash(
            request,
            "Kunne ikke finde koordinater. Angiv dem manuelt, hvis adressen er ukorrekt.",
            "error",
        )
    flash(request, "Adresse oprettet", "success")
    return RedirectResponse("/admin/addresses", status_code=303)


@router.get("/{address_id}/edit")
def edit_address_form(
    request: Request,
    address_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    latest_appointment = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id == address_id,
            models.Appointment.status.in_(
                [
                    models.AppointmentStatus.SCHEDULED,
                    models.AppointmentStatus.INFORMED,
                    models.AppointmentStatus.COMPLETED,
                    models.AppointmentStatus.CLOSED,
                    models.AppointmentStatus.NOT_HOME,
                    models.AppointmentStatus.NEEDS_RESCHEDULE,
                ]
            ),
        )
        .order_by(models.Appointment.starts_at.desc())
        .first()
    )
    current_year = datetime.utcnow().year
    status_label, status_key = status_label_and_key(latest_appointment, current_year)
    periods = (
        db.query(models.AddressUnavailablePeriod)
        .filter(models.AddressUnavailablePeriod.address_id == address_id)
        .order_by(models.AddressUnavailablePeriod.starts_at.desc())
        .all()
    )
    not_home_rows = (
        db.query(models.Appointment, models.User)
        .join(models.User, models.User.id == models.Appointment.contractor_id)
        .filter(
            models.Appointment.address_id == address_id,
            models.Appointment.status == models.AppointmentStatus.NOT_HOME,
        )
        .order_by(models.Appointment.starts_at.desc())
        .all()
    )
    not_home_history = [
        {"appointment": appointment, "contractor": contractor}
        for appointment, contractor in not_home_rows
    ]
    letter_appointment = (
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
    photos = (
        db.query(models.AppointmentPhoto)
        .filter(models.AppointmentPhoto.address_id == address_id)
        .order_by(models.AppointmentPhoto.created_at.desc())
        .all()
    )
    latest_response = (
        db.query(models.ResidentResponse)
        .filter(models.ResidentResponse.address_id == address_id)
        .order_by(models.ResidentResponse.created_at.desc())
        .first()
    )
    resident_response = None
    if latest_response:
        resident_response = {
            "label": RESPONSE_LABELS.get(latest_response.response_type, "Svar modtaget"),
            "date": latest_response.created_at.strftime("%d/%m/%Y"),
        }
    return request.app.state.templates.TemplateResponse(
        "admin_address_edit.html",
        {
            "request": request,
            "address": address,
            "current_user": user,
            "flashes": consume_flashes(request),
            "unavailable_periods": periods,
            "not_home_history": not_home_history,
            "letter_available": bool(letter_appointment),
            "photos": photos,
            "photo_labels": PHOTO_LABELS,
            "resident_response": resident_response,
            "status_label": status_label,
            "status_key": status_key,
        },
    )


@router.get("/{address_id}/edit/address")
def edit_address_fields_form(
    request: Request,
    address_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    return request.app.state.templates.TemplateResponse(
        "admin_address_fields_edit.html",
        {
            "request": request,
            "address": address,
            "current_user": user,
            "flashes": consume_flashes(request),
        },
    )


@router.post("/{address_id}/edit/address")
def update_address_fields(
    request: Request,
    address_id: int,
    street: str = Form(""),
    house_no: str = Form(""),
    zip_code: str = Form("", alias="zip"),
    city: str = Form(""),
    latitude: str | None = Form(None),
    longitude: str | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    street = street.strip()
    house_no = house_no.strip()
    zip_code = zip_code.strip()
    city = city.strip()

    if not all([street, house_no, zip_code, city]):
        flash(request, "Alle adressefelter skal udfyldes", "error")
        return RedirectResponse(
            f"/admin/addresses/{address_id}/edit/address", status_code=303
        )

    address.street = street
    address.house_no = house_no
    address.zip = zip_code
    address.city = city
    lat_value = (latitude or "").strip()
    lon_value = (longitude or "").strip()
    manual_coords: tuple[float, float] | None = None
    if lat_value or lon_value:
        try:
            manual_coords = (float(lat_value), float(lon_value))
        except ValueError:
            flash(request, "Ugyldige koordinater", "error")
            return RedirectResponse(
                f"/admin/addresses/{address_id}/edit/address", status_code=303
            )

    if manual_coords:
        address.latitude = manual_coords[0]
        address.longitude = manual_coords[1]
    else:
        coords = geocode_address(street, house_no, zip_code, city)
        if coords:
            address.latitude = coords[0]
            address.longitude = coords[1]
        else:
            address.latitude = None
            address.longitude = None
    db.commit()
    if not manual_coords and (address.latitude is None or address.longitude is None):
        flash(
            request,
            "Kunne ikke finde koordinater. Angiv dem manuelt, hvis adressen er ukorrekt.",
            "error",
        )
    flash(request, "Adressefelter opdateret", "success")
    return RedirectResponse(
        f"/admin/addresses/{address_id}/edit/address", status_code=303
    )


@router.get("/map")
def address_map(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    return request.app.state.templates.TemplateResponse(
        "admin_address_map.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "status_filters": STATUS_FILTERS,
        },
    )


@router.get("/map-data")
def address_map_data(
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    query = db.query(models.Address)
    search_value = (q or "").strip().lower()
    if search_value:
        pattern = f"%{search_value}%"
        query = query.filter(
            or_(
                func.lower(models.Address.street).like(pattern),
                func.lower(models.Address.house_no).like(pattern),
                func.lower(models.Address.zip).like(pattern),
                func.lower(models.Address.city).like(pattern),
                func.lower(models.Address.customer_name).like(pattern),
                func.lower(models.Address.customer_email).like(pattern),
                func.lower(models.Address.customer_phone).like(pattern),
            )
        )
    addresses = query.all()
    address_ids = [address.id for address in addresses]
    status_map = latest_status_map(db, address_ids)

    allowed_filters = {item["value"] for item in STATUS_FILTERS}
    selected_status = status if status in allowed_filters else "all"
    if selected_status != "all":
        filter_map = {
            "planned": {models.AppointmentStatus.SCHEDULED},
            "informed": {models.AppointmentStatus.INFORMED},
            "completed": {models.AppointmentStatus.COMPLETED},
            "closed": {models.AppointmentStatus.CLOSED},
            "not_home": {models.AppointmentStatus.NOT_HOME},
            "needs_reschedule": {models.AppointmentStatus.NEEDS_RESCHEDULE},
        }
        allowed_statuses = filter_map.get(selected_status, set())
        if selected_status == "unplanned":
            addresses = [
                address for address in addresses if address.id not in status_map
            ]
        elif selected_status == "not_home_history":
            not_home_rows = (
                db.query(models.Appointment.address_id)
                .filter(models.Appointment.status == models.AppointmentStatus.NOT_HOME)
                .distinct()
                .all()
            )
            not_home_ids = {row[0] for row in not_home_rows}
            addresses = [address for address in addresses if address.id in not_home_ids]
        else:
            addresses = [
                address
                for address in addresses
                if status_map.get(address.id) in allowed_statuses
            ]

    payload = []
    for address in addresses:
        status_value = status_map.get(address.id)
        payload.append(
            {
                "id": address.id,
                "street": address.street,
                "house_no": address.house_no,
                "zip": address.zip,
                "city": address.city,
                "latitude": float(address.latitude) if address.latitude is not None else None,
                "longitude": float(address.longitude) if address.longitude is not None else None,
                "status": status_value.value if status_value else "unplanned",
            }
        )
    return JSONResponse({"addresses": payload})


@router.get("/map-center")
def address_map_center(
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    coords = geocode_query("Gadevand, Hillerod, Denmark")
    if not coords:
        return JSONResponse({"success": False})
    return JSONResponse({"success": True, "latitude": coords[0], "longitude": coords[1]})


@router.post("/{address_id}/coordinates")
def update_address_coordinates(
    address_id: int,
    payload: CoordinatePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    address.latitude = payload.latitude
    address.longitude = payload.longitude
    db.commit()
    return JSONResponse({"success": True})


@router.post("/{address_id}/geocode")
def geocode_address_endpoint(
    address_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    coords = geocode_address(address.street, address.house_no, address.zip, address.city)
    if not coords:
        return JSONResponse({"success": False, "message": "Kunne ikke geokode"})

    address.latitude = coords[0]
    address.longitude = coords[1]
    db.commit()
    return JSONResponse(
        {
            "success": True,
            "latitude": float(coords[0]),
            "longitude": float(coords[1]),
        }
    )


@router.post("/{address_id}/edit")
def update_address(
    request: Request,
    address_id: int,
    customer_name: str | None = Form(None),
    customer_email: str | None = Form(None),
    customer_phone: str | None = Form(None),
    buffer_flag: bool = Form(False),
    buffer_note: str | None = Form(None),
    old_meter_no: str | None = Form(None),
    new_meter_no: str | None = Form(None),
    blocked_flag: bool = Form(False),
    blocked_note: str | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    customer_name = (customer_name or "").strip() or None
    customer_email = (customer_email or "").strip() or None
    customer_phone = (customer_phone or "").strip() or None
    buffer_note = (buffer_note or "").strip() or None
    old_meter_no = (old_meter_no or "").strip() or None
    new_meter_no = (new_meter_no or "").strip() or None
    blocked_note = (blocked_note or "").strip() or None
    blocked_reason = blocked_note if blocked_flag else None
    if blocked_flag and not blocked_reason:
        blocked_reason = "Fejl ved stophane"

    address.customer_name = customer_name
    address.customer_email = customer_email
    address.customer_phone = customer_phone
    address.buffer_flag = buffer_flag
    address.buffer_note = buffer_note
    address.old_meter_no = old_meter_no
    address.new_meter_no = new_meter_no
    address.blocked_reason = blocked_reason
    db.commit()
    flash(request, "Adresse opdateret", "success")
    return RedirectResponse("/admin/addresses", status_code=303)


@router.post("/{address_id}/unavailable")
def add_unavailable_period(
    request: Request,
    address_id: int,
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")

    try:
        starts_value = parse_datetime_local(starts_at)
        ends_value = parse_datetime_local(ends_at)
    except ValueError:
        flash(request, "Dato eller tidspunkt er ugyldigt", "error")
        return RedirectResponse(f"/admin/addresses/{address_id}/edit", status_code=303)

    if ends_value < starts_value:
        flash(request, "Slut skal være efter start", "error")
        return RedirectResponse(f"/admin/addresses/{address_id}/edit", status_code=303)

    note_value = note.strip() or None
    db.add(
        models.AddressUnavailablePeriod(
            address_id=address.id,
            starts_at=starts_value,
            ends_at=ends_value,
            note=note_value,
        )
    )
    db.commit()
    flash(request, "Ikke tilgængelig periode tilføjet", "success")
    return RedirectResponse(f"/admin/addresses/{address_id}/edit", status_code=303)


@router.post("/{address_id}/unavailable/{period_id}/delete")
def delete_unavailable_period(
    request: Request,
    address_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    period = (
        db.query(models.AddressUnavailablePeriod)
        .filter(
            models.AddressUnavailablePeriod.id == period_id,
            models.AddressUnavailablePeriod.address_id == address_id,
        )
        .first()
    )
    if not period:
        flash(request, "Periode ikke fundet", "error")
        return RedirectResponse(f"/admin/addresses/{address_id}/edit", status_code=303)

    db.delete(period)
    db.commit()
    flash(request, "Ikke tilgængelig periode slettet", "success")
    return RedirectResponse(f"/admin/addresses/{address_id}/edit", status_code=303)


@router.post("/{address_id}/needs-reschedule")
def mark_needs_reschedule(
    request: Request,
    address_id: int,
    note: str = Form(""),
    redirect: str = Form("/admin/addresses"),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    note_value = note.strip()
    if not note_value:
        flash(request, "Note er påkrævet", "error")
        return RedirectResponse(redirect, status_code=303)

    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.address_id == address_id)
        .order_by(models.Appointment.starts_at.desc())
        .first()
    )
    if not appointment:
        flash(request, "Adresse er ikke planlagt endnu", "error")
        return RedirectResponse(redirect, status_code=303)

    if appointment.status == models.AppointmentStatus.NOT_HOME:
        reschedule_start = appointment.starts_at + timedelta(seconds=1)
        reschedule_end = appointment.ends_at + timedelta(seconds=1)
        db.add(
            models.Appointment(
                address_id=appointment.address_id,
                contractor_id=appointment.contractor_id,
                starts_at=reschedule_start,
                ends_at=reschedule_end,
                status=models.AppointmentStatus.NEEDS_RESCHEDULE,
                notes=note_value,
                changed_date=datetime.utcnow(),
                changed_by_user_id=user.id,
            )
        )
    else:
        appointment.status = models.AppointmentStatus.NEEDS_RESCHEDULE
        appointment.notes = note_value
        appointment.changed_date = datetime.utcnow()
        appointment.changed_by_user_id = user.id
    db.commit()

    flash(request, "Status opdateret til behov for ny dato", "success")
    return RedirectResponse(redirect, status_code=303)


@router.post("/import")
def import_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN, models.UserRole.USER)),
):
    try:
        raw = file.file.read()
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        flash(request, "CSV-filen kunne ikke læses", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    required_fields = {"street", "house_no", "zip", "city"}
    if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
        flash(request, "CSV skal indeholde street, house_no, zip, city", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    created = 0
    skipped = 0
    try:
        for row in reader:
            street = (row.get("street") or "").strip()
            house_no = (row.get("house_no") or "").strip()
            zip_code = (row.get("zip") or "").strip()
            city = (row.get("city") or "").strip()
            customer_name = (row.get("customer_name") or "").strip() or None
            customer_email = (row.get("customer_email") or "").strip() or None
            customer_phone = (row.get("customer_phone") or "").strip() or None
            if not all([street, house_no, zip_code, city]):
                skipped += 1
                continue
            db.add(
                models.Address(
                    street=street,
                    house_no=house_no,
                    zip=zip_code,
                    city=city,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                )
            )
            created += 1
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        flash(request, "Der opstod en fejl under import", "error")
        return RedirectResponse("/admin/addresses", status_code=303)

    flash(request, f"Importerede {created} adresser, {skipped} sprunget over", "success")
    return RedirectResponse("/admin/addresses", status_code=303)
