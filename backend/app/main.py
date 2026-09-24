from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .admin_routes import router as reference_router
from .auth_routes import router as auth_router
from .api import router
from .config import settings
from .coverse_routes import router as coverse_router
from .erp_plan_routes import router as erp_plan_router
from .master_data_routes import router as master_data_router
from .payroll_routes import router as payroll_router
from .yandex_disk_routes import router as yandex_disk_router
from .user_admin_routes import router as user_admin_router
from .workspace_routes import router as workspace_router
from .reconciliation_routes import router as reconciliation_control_router
from .shift_master_routes import router as shift_master_router
from .production_manager_routes import router as production_manager_router
from .management_routes import router as management_router
from .problem_center_routes import router as problem_center_router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router)
app.include_router(coverse_router)
app.include_router(yandex_disk_router)
app.include_router(erp_plan_router)
app.include_router(master_data_router)
app.include_router(payroll_router)
app.include_router(reference_router)
app.include_router(user_admin_router)
app.include_router(workspace_router)
app.include_router(reconciliation_control_router)
app.include_router(shift_master_router)
app.include_router(production_manager_router)
app.include_router(management_router)
app.include_router(problem_center_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vitagroup-oee-api",
        "environment": settings.environment,
        "coverse_configured": bool(settings.coverse_api_token),
        "yandex_plan_configured": bool(settings.yandex_plan_public_url),
    }
