from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import CurrentUser, require_roles
from .reconciliation_service import (
    save_reconciliation_case,
    shift_reconciliation,
)

router = APIRouter(
    prefix="/api/v1/reconciliation-control",
    tags=["Reconciliation control"],
)


class CaseInput(BaseModel):
    status: str = Field(pattern="^(OPEN|EXPLAINED|RESOLVED)$")
    reason_code: str | None = None
    comment: str | None = Field(default=None, max_length=2000)


@router.get(
    "",
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
def control(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    try:
        return shift_reconciliation(business_date, shift_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{production_run_id}/case",
    dependencies=[
        Depends(
            require_roles(
                "SHIFT_MASTER",
                "PRODUCTION_MANAGER",
                "ACCOUNTANT_PRODUCTION",
                "ADMIN",
            )
        )
    ],
)
def save_case(
    production_run_id: UUID,
    payload: CaseInput,
    user: CurrentUser,
):
    try:
        return save_reconciliation_case(
            production_run_id=production_run_id,
            status=payload.status,
            reason_code=payload.reason_code,
            comment=payload.comment,
            user_id=UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
