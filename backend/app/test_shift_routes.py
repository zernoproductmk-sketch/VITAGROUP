from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import CurrentUser, require_roles
from .test_shift_service import (
    assign_run_staff,
    create_test_shift,
    test_shift_context,
)

router = APIRouter(
    prefix="/api/v1/test-shift",
    tags=["Test shift"],
    dependencies=[
        Depends(require_roles("PRODUCTION_MANAGER","ADMIN"))
    ],
)


class StaffAssignmentInput(BaseModel):
    employee_ids: list[UUID] = Field(min_length=1)


@router.get("")
def context(
    business_date: date,
    shift_code: str = Query(pattern="^(DAY|NIGHT)$"),
):
    try:
        return test_shift_context(business_date, shift_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create")
def create(
    business_date: date,
    user: CurrentUser,
    shift_code: str = Query(pattern="^(DAY|NIGHT)$"),
):
    try:
        return create_test_shift(
            business_date=business_date,
            shift_code=shift_code,
            user_id=UUID(user["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{production_run_id}/staff")
def assign_staff(
    production_run_id: UUID,
    payload: StaffAssignmentInput,
    user: CurrentUser,
):
    try:
        return assign_run_staff(
            production_run_id=production_run_id,
            employee_ids=payload.employee_ids,
            user_id=UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
