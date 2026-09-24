from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import CurrentUser, require_roles
from .norm_admin_service import norm_admin_data, save_manual_norm

router = APIRouter(
    prefix="/api/v1/admin/norms",
    tags=["Production norms administration"],
    dependencies=[Depends(require_roles("PRODUCTION_MANAGER","ADMIN"))],
)


class NormInput(BaseModel):
    id: UUID | None = None
    product_id: UUID
    equipment_id: UUID
    ideal_rate_per_hour: Decimal = Field(gt=0)
    valid_from: date
    valid_to: date | None = None
    apply_to_open_runs: bool = True


@router.get("")
def data():
    return norm_admin_data()


@router.post("")
def save(payload: NormInput, user: CurrentUser):
    try:
        return save_manual_norm(
            norm_id=payload.id,
            product_id=payload.product_id,
            equipment_id=payload.equipment_id,
            ideal_rate_per_hour=payload.ideal_rate_per_hour,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            apply_to_open_runs=payload.apply_to_open_runs,
            user_id=UUID(user["id"]),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
