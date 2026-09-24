from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_roles
from .shift_master_service import shift_master_dashboard

router = APIRouter(
    prefix="/api/v1/shift-master",
    tags=["Shift master"],
    dependencies=[
        Depends(
            require_roles(
                "SHIFT_MASTER",
                "PRODUCTION_MANAGER",
                "MANAGEMENT",
                "ADMIN",
            )
        )
    ],
)


@router.get("/dashboard")
def dashboard(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    try:
        return shift_master_dashboard(
            business_date,
            shift_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
