from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_roles
from .reason_admin_service import (
    list_reasons,
    upsert_defect_reason,
    upsert_downtime_reason,
)

router = APIRouter(
    prefix="/api/v1/admin/reasons",
    tags=["Reason administration"],
    dependencies=[Depends(require_roles("ADMIN","PRODUCTION_MANAGER"))],
)


class DowntimeReasonInput(BaseModel):
    id: UUID | None = None
    code: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    affects_availability: bool = True
    is_planned: bool = False
    is_active: bool = True


class DefectReasonInput(BaseModel):
    id: UUID | None = None
    code: str = Field(min_length=1, max_length=80)
    category: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    is_active: bool = True


@router.get("")
def reasons():
    return list_reasons()


@router.post("/downtime")
def save_downtime(payload: DowntimeReasonInput):
    try:
        return upsert_downtime_reason(
            reason_id=payload.id,
            code=payload.code,
            category=payload.category,
            name=payload.name,
            affects_availability=payload.affects_availability,
            is_planned=payload.is_planned,
            is_active=payload.is_active,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/defect")
def save_defect(payload: DefectReasonInput):
    try:
        return upsert_defect_reason(
            reason_id=payload.id,
            code=payload.code,
            category=payload.category,
            name=payload.name,
            is_active=payload.is_active,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
