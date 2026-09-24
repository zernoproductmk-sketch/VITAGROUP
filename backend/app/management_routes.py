from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_roles
from .management_service import management_overview

router = APIRouter(
    prefix="/api/v1/management",
    tags=["Management"],
    dependencies=[
        Depends(
            require_roles(
                "MANAGEMENT",
                "PRODUCTION_MANAGER",
                "ADMIN",
            )
        )
    ],
)


@router.get("/overview")
def overview(
    end_date: date | None = None,
    days: int = Query(default=14),
):
    try:
        return management_overview(end_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
