from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.dependencies import consume_flashes, require_role

router = APIRouter(prefix="/vvs", tags=["vvs"])


@router.get("")
def vvs_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role(models.UserRole.VVS)),
):
    return request.app.state.templates.TemplateResponse(
        "vvs_dashboard.html",
        {
            "request": request,
            "current_user": user,
            "flashes": consume_flashes(request),
        },
    )
