from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import CurrentUser, require_roles
from .shift_master_service import (
    close_shift,
    complete_production_run,
    shift_close_readiness,
    shift_master_dashboard,
)

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


@router.get("/close-readiness")
def close_readiness(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    try:
        return shift_close_readiness(
            business_date,
            shift_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/close",
    dependencies=[
        Depends(
            require_roles(
                "SHIFT_MASTER",
                "PRODUCTION_MANAGER",
                "ADMIN",
            )
        )
    ],
)
def close(
    business_date: date,
    shift_code: str,
    user: CurrentUser,
):
    try:
        return close_shift(
            business_date,
            shift_code,
            UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/runs/{production_run_id}/complete",
    dependencies=[
        Depends(
            require_roles(
                "SHIFT_MASTER",
                "PRODUCTION_MANAGER",
                "ADMIN",
            )
        )
    ],
)
def complete_run(
    production_run_id: UUID,
    user: CurrentUser,
):
    try:
        return complete_production_run(
            production_run_id,
            UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
