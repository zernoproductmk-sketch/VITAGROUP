from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_roles
from .shift_lifecycle_service import shift_lifecycle_status

router = APIRouter(
    prefix="/api/v1/shift-lifecycle",
    tags=["Shift lifecycle"],
    dependencies=[
        Depends(
            require_roles(
                "PRODUCTION_MANAGER",
                "MANAGEMENT",
                "ADMIN",
            )
        )
    ],
)


@router.get("")
def status(
    business_date: date,
    shift_code: str = Query(pattern="^(DAY|NIGHT)$"),
):
    try:
        return shift_lifecycle_status(
            business_date,
            shift_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
