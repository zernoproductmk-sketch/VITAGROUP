from fastapi import APIRouter, Depends

from .auth import require_roles
from .launch_readiness_service import launch_readiness

router = APIRouter(
    prefix="/api/v1/launch-readiness",
    tags=["Launch readiness"],
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


@router.get("")
def readiness():
    return launch_readiness()
