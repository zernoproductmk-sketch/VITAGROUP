from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import require_roles
from .payroll_service import (
    BASIS_LABELS,
    calculate_period,
    list_periods,
    payroll_preview,
    rate_options,
    save_allocation,
    save_product_attributes,
    upsert_period,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["Payroll"])

PAYROLL_READ_ROLES = ("ECONOMIST", "MANAGEMENT", "ADMIN")
PAYROLL_EDIT_ROLES = ("ECONOMIST", "ADMIN")


class PeriodInput(BaseModel):
    date_from: date
    date_to: date
    quantity_basis: str | None = None
    notes: str | None = None


class ProductAttributesInput(BaseModel):
    product_type: str | None = None
    print_flag: str | None = None
    tariff_group: str | None = None


class AllocationEntry(BaseModel):
    employee_id: UUID
    allocation_factor: float = Field(gt=0, le=1)


class AllocationInput(BaseModel):
    entries: list[AllocationEntry]


@router.get(
    "/settings",
    dependencies=[Depends(require_roles(*PAYROLL_READ_ROLES))],
)
def settings():
    return {
        "quantity_bases": [
            {"code": code, "label": label}
            for code, label in BASIS_LABELS.items()
        ]
    }


@router.get(
    "/periods",
    dependencies=[Depends(require_roles(*PAYROLL_READ_ROLES))],
)
def periods(limit: int = Query(default=24, ge=1, le=100)):
    return {"rows": list_periods(limit)}


@router.post(
    "/periods",
    dependencies=[Depends(require_roles(*PAYROLL_EDIT_ROLES))],
)
def period(payload: PeriodInput):
    try:
        return upsert_period(
            payload.date_from,
            payload.date_to,
            payload.quantity_basis,
            payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/preview",
    dependencies=[Depends(require_roles(*PAYROLL_READ_ROLES))],
)
def preview(
    date_from: date,
    date_to: date,
    quantity_basis: str | None = None,
):
    try:
        return payroll_preview(date_from, date_to, quantity_basis)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/periods/{period_id}/calculate",
    dependencies=[Depends(require_roles(*PAYROLL_EDIT_ROLES))],
)
def calculate(period_id: UUID):
    try:
        return calculate_period(period_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/rate-options",
    dependencies=[Depends(require_roles(*PAYROLL_READ_ROLES))],
)
def payroll_rate_options(
    equipment_id: UUID,
    business_date: date,
):
    return rate_options(equipment_id, business_date)


@router.post(
    "/products/{product_id}/attributes",
    dependencies=[Depends(require_roles(*PAYROLL_EDIT_ROLES))],
)
def product_attributes(
    product_id: UUID,
    payload: ProductAttributesInput,
):
    try:
        return save_product_attributes(
            product_id,
            payload.product_type,
            payload.print_flag,
            payload.tariff_group,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/allocation",
    dependencies=[Depends(require_roles(*PAYROLL_EDIT_ROLES))],
)
def allocation(run_id: UUID, payload: AllocationInput):
    try:
        return save_allocation(
            run_id,
            [
                {
                    "employee_id": item.employee_id,
                    "allocation_factor": item.allocation_factor,
                }
                for item in payload.entries
            ],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
