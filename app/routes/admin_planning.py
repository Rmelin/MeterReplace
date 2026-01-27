from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/planning", tags=["admin"])


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


@dataclass
class PlannedSlot:
    address: models.Address
    contractor: models.User
    starts_at: datetime
    ends_at: datetime


@dataclass
class BufferEntry:
    orig: int
    latest: int
    address: models.Address


def parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_time(raw: str) -> time:
    return datetime.strptime(raw, "%H:%M").time()


def build_slots(db: Session, plan_date: date) -> list[tuple[models.User, datetime, datetime]]:
    availability = (
        db.query(models.VvsAvailability, models.User)
        .join(models.User, models.User.id == models.VvsAvailability.user_id)
        .filter(models.VvsAvailability.date == plan_date)
        .order_by(models.User.username)
        .all()
    )
    slots: list[tuple[models.User, datetime, datetime]] = []
    windows = [(time(8, 0), time(12, 0)), (time(12, 0), time(16, 0))]

    for entry, contractor in availability:
        for window_start, window_end in windows:
            start = max(entry.start_time, window_start)
            end = min(entry.end_time, window_end)
            if start >= end:
                continue
            current = datetime.combine(plan_date, start)
            end_dt = datetime.combine(plan_date, end)
            while current + timedelta(minutes=30) <= end_dt:
                slots.append((contractor, current, current + timedelta(minutes=30)))
                current += timedelta(minutes=30)

    slots.sort(key=lambda item: (item[1], item[0].username))
    return slots


def available_stock(db: Session) -> int:
    return (
        db.query(func.coalesce(func.sum(models.StockMovement.quantity), 0)).scalar() or 0
    )


def apply_buffer_rule(
    addresses: list[models.Address], limit: int = 14
) -> list[models.Address]:
    return addresses


def latest_status_map(db: Session, address_ids: list[int]) -> dict[int, models.AppointmentStatus]:
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


def unavailable_address_ids(db: Session, plan_date: date) -> set[int]:
    day_start = datetime.combine(plan_date, time.min)
    day_end = datetime.combine(plan_date, time.max)
    rows = (
        db.query(models.AddressUnavailablePeriod.address_id)
        .filter(
            models.AddressUnavailablePeriod.starts_at <= day_end,
            models.AddressUnavailablePeriod.ends_at >= day_start,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def fetch_addresses(
    db: Session, plan_date: date | None = None
) -> tuple[list[models.Address], set[int]]:
    scheduled = select(models.Appointment.address_id).where(
        models.Appointment.status.in_(
            [
                models.AppointmentStatus.SCHEDULED,
                models.AppointmentStatus.INFORMED,
                models.AppointmentStatus.COMPLETED,
                models.AppointmentStatus.CLOSED,
            ]
        )
    )
    query = (
        db.query(models.Address)
        .filter(~models.Address.id.in_(scheduled))
        .filter(models.Address.blocked_reason.is_(None))
    )
    if plan_date:
        unavailable_ids = unavailable_address_ids(db, plan_date)
        if unavailable_ids:
            query = query.filter(~models.Address.id.in_(unavailable_ids))
    addresses = query.all()
    priority_map = street_priority_map(db)
    sorted_addresses = sorted(addresses, key=lambda address: address_sort_key(address, priority_map))
    status_map = latest_status_map(db, [address.id for address in sorted_addresses])
    reschedule_ids = {
        address_id
        for address_id, status in status_map.items()
        if status == models.AppointmentStatus.NEEDS_RESCHEDULE
    }

    reschedule_addresses = [
        address for address in sorted_addresses if address.id in reschedule_ids
    ]
    remaining = [
        address for address in sorted_addresses if address.id not in reschedule_ids
    ]
    ordered_remaining = apply_buffer_rule(remaining, limit=14)
    return reschedule_addresses + ordered_remaining, reschedule_ids


def fetch_skipped_addresses(
    db: Session, plan_date: date | None = None
) -> tuple[list[models.Address], list[models.Address]]:
    scheduled = select(models.Appointment.address_id).where(
        models.Appointment.status.in_(
            [
                models.AppointmentStatus.SCHEDULED,
                models.AppointmentStatus.INFORMED,
                models.AppointmentStatus.COMPLETED,
                models.AppointmentStatus.CLOSED,
            ]
        )
    )
    base_query = db.query(models.Address).filter(~models.Address.id.in_(scheduled))
    if plan_date:
        unavailable_ids = unavailable_address_ids(db, plan_date)
        if unavailable_ids:
            base_query = base_query.filter(~models.Address.id.in_(unavailable_ids))
    priority_map = street_priority_map(db)
    blocked_addresses = (
        base_query.filter(models.Address.blocked_reason.is_not(None)).all()
    )
    buffer_addresses = (
        base_query.filter(
            models.Address.blocked_reason.is_(None),
            models.Address.buffer_flag.is_(True),
        ).all()
    )
    blocked_sorted = sorted(
        blocked_addresses, key=lambda address: address_sort_key(address, priority_map)
    )
    buffer_sorted = sorted(
        buffer_addresses, key=lambda address: address_sort_key(address, priority_map)
    )
    return blocked_sorted, buffer_sorted


def fetch_unavailable_periods(
    db: Session, plan_date: date
) -> list[dict[str, object]]:
    day_start = datetime.combine(plan_date, time.min)
    day_end = datetime.combine(plan_date, time.max)
    rows = (
        db.query(models.AddressUnavailablePeriod, models.Address)
        .join(models.Address, models.Address.id == models.AddressUnavailablePeriod.address_id)
        .filter(
            models.AddressUnavailablePeriod.starts_at <= day_end,
            models.AddressUnavailablePeriod.ends_at >= day_start,
        )
        .order_by(models.AddressUnavailablePeriod.starts_at)
        .all()
    )
    return [
        {
            "address": address,
            "starts_at": period.starts_at,
            "ends_at": period.ends_at,
            "note": period.note,
        }
        for period, address in rows
    ]


def available_vvs_for_date(db: Session, plan_date: date) -> list[models.User]:
    return (
        db.query(models.User)
        .join(models.VvsAvailability, models.VvsAvailability.user_id == models.User.id)
        .filter(
            models.User.role == models.UserRole.VVS,
            models.VvsAvailability.date == plan_date,
        )
        .order_by(models.User.username)
        .all()
    )


def availability_for_user(db: Session, user_id: int, plan_date: date) -> models.VvsAvailability | None:
    return (
        db.query(models.VvsAvailability)
        .filter(
            models.VvsAvailability.user_id == user_id,
            models.VvsAvailability.date == plan_date,
        )
        .first()
    )


def has_conflict(db: Session, contractor_id: int, starts_at: datetime, ends_at: datetime) -> bool:
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.contractor_id == contractor_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.starts_at < ends_at,
            models.Appointment.ends_at > starts_at,
        )
        .first()
        is not None
    )


def compute_plan_from_addresses(
    db: Session, plan_date: date, addresses: list[models.Address]
) -> tuple[list[PlannedSlot], list[models.Address], int, int]:
    slots = build_slots(db, plan_date)
    stock = available_stock(db)
    max_count = min(len(slots), len(addresses), stock)
    planned: list[PlannedSlot] = []

    for idx in range(max_count):
        contractor, starts_at, ends_at = slots[idx]
        planned.append(
            PlannedSlot(
                address=addresses[idx],
                contractor=contractor,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )

    unplanned = addresses[max_count:]
    return planned, unplanned, stock, len(slots)


def compute_plan(db: Session, plan_date: date) -> tuple[list[PlannedSlot], list[models.Address], int, int, set[int]]:
    slots = build_slots(db, plan_date)
    addresses, reschedule_ids = fetch_addresses(db, plan_date)
    stock = available_stock(db)
    max_count = min(len(slots), len(addresses), stock)
    planned: list[PlannedSlot] = []

    for idx in range(max_count):
        contractor, starts_at, ends_at = slots[idx]
        planned.append(
            PlannedSlot(
                address=addresses[idx],
                contractor=contractor,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )

    unplanned = addresses[max_count:]
    return planned, unplanned, stock, len(slots), reschedule_ids


def available_planning_dates(db: Session) -> list[dict[str, object]]:
    rows = (
        db.query(models.VvsAvailability.date)
        .distinct()
        .order_by(models.VvsAvailability.date)
        .all()
    )
    options: list[dict[str, object]] = []
    for (availability_date,) in rows:
        slot_count = len(build_slots(db, availability_date))
        if slot_count == 0:
            continue
        day_start = datetime.combine(availability_date, time.min)
        day_end = datetime.combine(availability_date, time.max)
        scheduled_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
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
                models.Appointment.starts_at >= day_start,
                models.Appointment.starts_at <= day_end,
            )
            .scalar()
            or 0
        )
        label = (
            f"{availability_date.strftime('%d/%m/%Y')} "
            f"({scheduled_count} planlagt ud af {slot_count} mulighed)"
        )
        options.append(
            {
                "value": availability_date.isoformat(),
                "label": label,
                "slot_count": slot_count,
            }
        )
    return options


@router.get("")
def planning_form(
    request: Request,
    date_query: str | None = None,
    preview: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    planned: list[PlannedSlot] = []
    unplanned: list[models.Address] = []
    stock = 0
    slot_count = 0
    plan_date = None

    options = available_planning_dates(db)
    option_values = {option["value"] for option in options}

    if date_query:
        try:
            plan_date = parse_date(date_query)
        except ValueError:
            flash(request, "Dato er ugyldig", "error")
            return RedirectResponse("/admin/planning", status_code=303)

    if plan_date and plan_date.isoformat() not in option_values:
        flash(request, "Vælg en dato med arbejdsdage", "error")
        return RedirectResponse("/admin/planning", status_code=303)

    ordered_addresses: list[models.Address] = []
    reschedule_ids: set[int] = set()
    skipped_blocked: list[models.Address] = []
    skipped_buffer: list[models.Address] = []
    unavailable_entries: list[dict[str, object]] = []
    scheduled_addresses: list[models.Address] = []
    if plan_date and preview:
        planned, unplanned, stock, slot_count, reschedule_ids = compute_plan(db, plan_date)
        ordered_addresses, _ = fetch_addresses(db, plan_date)
        skipped_blocked, skipped_buffer = fetch_skipped_addresses(db, plan_date)
        unavailable_entries = fetch_unavailable_periods(db, plan_date)
        unavailable_ids = {entry["address"].id for entry in unavailable_entries}
        for address in skipped_blocked:
            if address.id in unavailable_ids:
                continue
            unavailable_entries.append(
                {
                    "address": address,
                    "starts_at": None,
                    "ends_at": None,
                    "note": address.blocked_reason,
                }
            )

    if plan_date:
        scheduled_rows = (
            db.query(models.Address)
            .join(models.Appointment, models.Appointment.address_id == models.Address.id)
            .filter(
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.starts_at >= datetime.combine(plan_date, time.min),
                models.Appointment.starts_at <= datetime.combine(plan_date, time.max),
            )
            .order_by(models.Appointment.starts_at)
            .all()
        )
        scheduled_addresses = scheduled_rows

    total_addresses = len(planned) + len(unplanned)

    return request.app.state.templates.TemplateResponse(
        "admin_planning.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "planned": planned,
            "unplanned": unplanned,
            "stock": stock,
            "slot_count": slot_count,
            "plan_date": plan_date,
            "total_addresses": total_addresses,
            "date_options": options,
            "ordered_addresses": ordered_addresses,
            "unavailable_entries": unavailable_entries,
            "skipped_buffer": skipped_buffer,
            "scheduled_addresses": scheduled_addresses,
        },
    )


@router.post("/preview")
def preview_plan(
    request: Request,
    date_raw: str = Form(""),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    if not date_raw:
        flash(request, "Vælg en dato", "error")
        return RedirectResponse("/admin/planning", status_code=303)
    return RedirectResponse(
        f"/admin/planning?date_query={date_raw}&preview=1", status_code=303
    )


@router.post("/commit")
def commit_plan(
    request: Request,
    date_raw: str = Form(""),
    address_order: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    if not date_raw:
        flash(request, "Vælg en dato", "error")
        return RedirectResponse("/admin/planning", status_code=303)

    options = available_planning_dates(db)
    option_values = {option["value"] for option in options}

    if date_raw not in option_values:
        flash(request, "Vælg en dato med arbejdsdage", "error")
        return RedirectResponse("/admin/planning", status_code=303)

    try:
        plan_date = parse_date(date_raw)
    except ValueError:
        flash(request, "Dato er ugyldig", "error")
        return RedirectResponse("/admin/planning", status_code=303)

    planned: list[PlannedSlot]
    unplanned: list[models.Address]
    stock: int
    slot_count: int

    ordered_ids = [
        int(value)
        for value in address_order.split(",")
        if value.strip().isdigit()
    ]
    if ordered_ids:
        addresses, _ = fetch_addresses(db, plan_date)
        address_map = {address.id: address for address in addresses}
        if any(address_id not in address_map for address_id in ordered_ids):
            flash(request, "Rækkefølgen indeholder ugyldige adresser", "error")
            return RedirectResponse(
                f"/admin/planning?date_query={date_raw}&preview=1", status_code=303
            )
        if len(ordered_ids) != len(address_map):
            flash(request, "Rækkefølgen matcher ikke alle adresser", "error")
            return RedirectResponse(
                f"/admin/planning?date_query={date_raw}&preview=1", status_code=303
            )
        ordered_addresses = [address_map[address_id] for address_id in ordered_ids]
        planned, unplanned, stock, slot_count = compute_plan_from_addresses(
            db, plan_date, ordered_addresses
        )
    else:
        planned, unplanned, stock, slot_count, _ = compute_plan(db, plan_date)

    if slot_count == 0:
        flash(request, "Ingen arbejdsdage på denne dato", "error")
        return RedirectResponse(f"/admin/planning?date_query={date_raw}&preview=1", status_code=303)
    if not planned:
        flash(request, "Ingen slots kunne planlægges", "error")
        return RedirectResponse(f"/admin/planning?date_query={date_raw}&preview=1", status_code=303)

    for slot in planned:
        db.add(
            models.Appointment(
                address_id=slot.address.id,
                contractor_id=slot.contractor.id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                status=models.AppointmentStatus.SCHEDULED,
                changed_date=datetime.utcnow(),
                changed_by_user_id=user.id,
            )
        )

    db.add(
        models.StockMovement(
            movement_type=models.InventoryMovementType.RESERVE,
            quantity=-len(planned),
            created_by_user_id=user.id,
            note=f"Auto-planlægning {plan_date.isoformat()}",
        )
    )
    db.commit()

    remaining = len(unplanned)
    flash(
        request,
        f"Planlagt {len(planned)} adresser. {remaining} tilbage.",
        "success",
    )
    return RedirectResponse(f"/admin/planning?date_query={date_raw}&preview=1", status_code=303)


@router.get("/manual")
def manual_planning_form(
    request: Request,
    date_query: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    options = available_planning_dates(db)
    option_values = {option["value"] for option in options}
    plan_date = None
    vvs_users: list[models.User] = []
    addresses: list[models.Address] = []

    if date_query:
        try:
            plan_date = parse_date(date_query)
        except ValueError:
            flash(request, "Dato er ugyldig", "error")
            return RedirectResponse("/admin/planning/manual", status_code=303)

    scheduled_map: dict[int, list[dict[str, object]]] = {}

    if plan_date and plan_date.isoformat() in option_values:
        vvs_users = available_vvs_for_date(db, plan_date)
        addresses, _ = fetch_addresses(db, plan_date)
        if not vvs_users:
            flash(request, "VVS har ingen arbejdsdage", "error")
            return RedirectResponse("/admin/planning/manual", status_code=303)
        appointments = (
            db.query(models.Appointment, models.Address)
            .join(models.Address, models.Address.id == models.Appointment.address_id)
            .filter(
                models.Appointment.contractor_id.in_([user.id for user in vvs_users]),
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.starts_at >= datetime.combine(plan_date, time.min),
                models.Appointment.starts_at < datetime.combine(plan_date, time.max),
            )
            .order_by(models.Appointment.starts_at)
            .all()
        )
        for appointment, address in appointments:
            scheduled_map.setdefault(appointment.contractor_id, []).append(
                {
                    "starts_at": appointment.starts_at,
                    "ends_at": appointment.ends_at,
                    "address": f"{address.street} {address.house_no}, {address.zip} {address.city}",
                }
            )

    return request.app.state.templates.TemplateResponse(
        "admin_manual_planning.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "date_options": options,
            "plan_date": plan_date,
            "vvs_users": vvs_users,
            "addresses": addresses,
            "scheduled_map": scheduled_map,
        },
    )


@router.post("/manual")
def manual_planning_commit(
    request: Request,
    date_raw: str = Form(""),
    address_id: int = Form(0),
    contractor_id: int = Form(0),
    start_raw: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    if not date_raw:
        flash(request, "Vælg en dato", "error")
        return RedirectResponse("/admin/planning/manual", status_code=303)

    options = available_planning_dates(db)
    option_values = {option["value"] for option in options}
    if date_raw not in option_values:
        flash(request, "Vælg en dato med arbejdsdage", "error")
        return RedirectResponse("/admin/planning/manual", status_code=303)

    try:
        plan_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
    except ValueError:
        flash(request, "Dato eller tid er ugyldig", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    if address_id <= 0 or contractor_id <= 0:
        flash(request, "Vælg adresse og VVS", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    if available_stock(db) <= 0:
        flash(request, "Ingen lager tilbage", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    address = db.query(models.Address).filter(models.Address.id == address_id).first()
    if not address:
        flash(request, "Adresse findes ikke", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    existing = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.address_id == address_id,
            models.Appointment.status.in_(
                [models.AppointmentStatus.SCHEDULED, models.AppointmentStatus.COMPLETED]
            ),
        )
        .first()
    )
    if existing:
        flash(request, "Adresse er allerede planlagt", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    contractor = db.query(models.User).filter(models.User.id == contractor_id).first()
    if not contractor or contractor.role != models.UserRole.VVS:
        flash(request, "Ugyldig VVS", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    availability = availability_for_user(db, contractor_id, plan_date)
    if not availability:
        flash(request, "VVS har ingen arbejdsdage", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    slot_start = datetime.combine(plan_date, start_time)
    slot_end = slot_start + timedelta(minutes=30)
    window_start = time(8, 0)
    window_end = time(16, 0)

    if not (window_start <= start_time < window_end):
        flash(request, "Tid skal være mellem 08:00 og 16:00", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    if not (availability.start_time <= start_time < availability.end_time):
        flash(request, "Tid ligger udenfor arbejdsdag", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    if slot_end.time() > availability.end_time:
        flash(request, "Slot slutter udenfor arbejdsdag", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    if has_conflict(db, contractor_id, slot_start, slot_end):
        flash(request, "VVS er allerede planlagt på dette tidspunkt", "error")
        return RedirectResponse(
            f"/admin/planning/manual?date_query={date_raw}", status_code=303
        )

    db.add(
        models.Appointment(
            address_id=address.id,
            contractor_id=contractor.id,
            starts_at=slot_start,
            ends_at=slot_end,
            status=models.AppointmentStatus.SCHEDULED,
            changed_date=datetime.utcnow(),
            changed_by_user_id=user.id,
        )
    )
    db.add(
        models.StockMovement(
            movement_type=models.InventoryMovementType.RESERVE,
            quantity=-1,
            created_by_user_id=user.id,
            note=f"Manuel planlægning {plan_date.isoformat()}",
        )
    )
    db.commit()

    flash(request, "Adresse planlagt", "success")
    return RedirectResponse(
        f"/admin/planning/manual?date_query={date_raw}", status_code=303
    )
