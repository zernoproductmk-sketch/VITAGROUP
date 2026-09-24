from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_roles
from .problem_center_service import problem_center

router = APIRouter(
    prefix="/api/v1/problem-center",
    tags=["Problem center"],
    dependencies=[
        Depends(
            require_roles(
                "SHIFT_MASTER",
                "PRODUCTION_MANAGER",
                "ACCOUNTANT_PRODUCTION",
                "ECONOMIST",
                "MANAGEMENT",
                "ADMIN",
            )
        )
    ],
)


@router.get("")
def problems(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    try:
        return problem_center(
            business_date,
            shift_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
