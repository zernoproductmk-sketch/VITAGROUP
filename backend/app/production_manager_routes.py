from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from .auth import CurrentUser, require_roles
from .production_manager_service import production_manager_day, verify_shift

router = APIRouter(
    prefix="/api/v1/production-manager",
    tags=["Production manager"],
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


@router.get("/day")
def day(business_date: date):
    return production_manager_day(business_date)


@router.post("/verify-shift")
def verify(
    business_date: date,
    shift_code: str,
    user: CurrentUser,
):
    try:
        return verify_shift(
            business_date,
            shift_code,
            UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
