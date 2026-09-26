from fastapi import APIRouter, Depends, HTTPException

from .auth import require_roles
from .config import settings
from .erp_plan_import import (
    import_yandex_plan,
    import_yandex_plan_folder,
    latest_yandex_plan_batch,
    yandex_plan_preview,
)

router = APIRouter(
    prefix="/api/v1/integrations/yandex-disk",
    tags=["Yandex Disk"],
)


@router.get(
    "/status",
    dependencies=[
        Depends(
            require_roles(
                "ACCOUNTANT_PRODUCTION",
                "PRODUCTION_MANAGER",
                "ECONOMIST",
                "MANAGEMENT",
                "ADMIN",
            )
        )
    ],
)
def status():
    return {
        "configured": bool(settings.yandex_plan_public_url.strip()),
        "resource_path_configured": bool(settings.yandex_plan_resource_path.strip()),
        "last_import": latest_yandex_plan_batch(),
    }


@router.post(
    "/preview",
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
async def preview():
    try:
        return await yandex_plan_preview()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/import",
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
async def import_plan():
    try:
        return await import_yandex_plan_folder()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
