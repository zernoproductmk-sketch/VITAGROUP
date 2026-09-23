from fastapi import APIRouter, Query

from .erp_plan_promotion import (
    erp_plan_rows,
    erp_plan_summary,
    promote_erp_plan,
)

router = APIRouter(prefix="/api/v1/erp-plan", tags=["ERP plan"])


@router.get("/summary")
def summary():
    return erp_plan_summary()


@router.get("/rows")
def rows(limit: int = Query(default=300, ge=1, le=2000)):
    return {"rows": erp_plan_rows(limit)}


@router.post("/promote")
def promote(limit: int = Query(default=1000, ge=1, le=5000)):
    return promote_erp_plan(limit)
