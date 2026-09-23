from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .admin_routes import router as reference_router
from .api import router
from .config import settings
from .coverse_routes import router as coverse_router
from .master_data_routes import router as master_data_router

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

app.include_router(router)
app.include_router(coverse_router)
app.include_router(master_data_router)
app.include_router(reference_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vitagroup-oee-api",
        "environment": settings.environment,
        "coverse_configured": bool(settings.coverse_api_token),
    }
