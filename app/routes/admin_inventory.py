from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, flash, require_role

router = APIRouter(prefix="/admin/inventory", tags=["admin"])


@router.get("")
def inventory_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    stock = (
        db.query(func.coalesce(func.sum(models.StockMovement.quantity), 0))
        .scalar()
        or 0
    )
    batches = (
        db.query(models.MeterBatch)
        .order_by(models.MeterBatch.purchased_at.desc())
        .limit(20)
        .all()
    )
    movements = (
        db.query(models.StockMovement)
        .order_by(models.StockMovement.created_at.desc())
        .limit(20)
        .all()
    )
    movement_labels = {
        models.InventoryMovementType.PURCHASE: "Indkøb",
        models.InventoryMovementType.RESERVE: "Reserveret",
        models.InventoryMovementType.RELEASE: "Frigivet",
        models.InventoryMovementType.ADJUST: "Justering",
    }

    return request.app.state.templates.TemplateResponse(
        "admin_inventory.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
            "stock": stock,
            "batches": batches,
            "movements": movements,
            "movement_labels": movement_labels,
        },
    )


@router.post("")
def add_batch(
    request: Request,
    quantity: int = Form(0),
    reference: str = Form(""),
    meter_type: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    reference = reference.strip() or None
    meter_type = meter_type.strip() or None
    note = note.strip() or None

    if quantity <= 0:
        flash(request, "Antal skal være større end 0", "error")
        return RedirectResponse("/admin/inventory", status_code=303)

    batch = models.MeterBatch(
        quantity=quantity,
        reference=reference,
        meter_type=meter_type,
        note=note,
        created_by_user_id=user.id,
    )
    movement = models.StockMovement(
        movement_type=models.InventoryMovementType.PURCHASE,
        quantity=quantity,
        batch_id=None,
        created_by_user_id=user.id,
        note=note,
    )
    db.add(batch)
    db.flush()
    movement.batch_id = batch.id
    db.add(movement)
    db.commit()

    flash(request, f"Lager opdateret med {quantity} målere", "success")
    return RedirectResponse("/admin/inventory", status_code=303)


@router.post("/adjust")
def adjust_stock(
    request: Request,
    quantity: int = Form(0),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.ADMIN)),
):
    note_value = note.strip()
    if quantity <= 0:
        flash(request, "Antal skal være større end 0", "error")
        return RedirectResponse("/admin/inventory", status_code=303)
    if not note_value:
        flash(request, "Note er påkrævet", "error")
        return RedirectResponse("/admin/inventory", status_code=303)

    movement = models.StockMovement(
        movement_type=models.InventoryMovementType.ADJUST,
        quantity=-quantity,
        created_by_user_id=user.id,
        note=note_value,
    )
    db.add(movement)
    db.commit()

    flash(request, f"Lager justeret med -{quantity}", "success")
    return RedirectResponse("/admin/inventory", status_code=303)
