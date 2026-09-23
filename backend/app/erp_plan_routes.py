from fastapi import APIRouter, Depends, Query

from .auth import require_roles
from .erp_plan_promotion import (
    erp_plan_rows,
    erp_plan_summary,
    promote_erp_plan,
)

router = APIRouter(prefix="/api/v1/erp-plan", tags=["ERP plan"])

ERP_READ_ROLES = (
    "ACCOUNTANT_PRODUCTION",
    "PRODUCTION_MANAGER",
    "ECONOMIST",
    "MANAGEMENT",
    "ADMIN",
)


@router.get(
    "/summary",
    dependencies=[Depends(require_roles(*ERP_READ_ROLES))],
)
def summary():
    return erp_plan_summary()


@router.get(
    "/rows",
    dependencies=[Depends(require_roles(*ERP_READ_ROLES))],
)
def rows(limit: int = Query(default=300, ge=1, le=2000)):
    return {"rows": erp_plan_rows(limit)}


@router.post(
    "/promote",
    dependencies=[
        Depends(
            require_roles(
                "ACCOUNTANT_PRODUCTION",
                "PRODUCTION_MANAGER",
                "ADMIN",
            )
        )
    ],
)
def promote(limit: int = Query(default=1000, ge=1, le=5000)):
    return promote_erp_plan(limit)
