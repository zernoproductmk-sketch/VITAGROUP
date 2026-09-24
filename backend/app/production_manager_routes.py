from datetime import date

from fastapi import APIRouter, Depends

from .auth import require_roles
from .production_manager_service import production_manager_day

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
