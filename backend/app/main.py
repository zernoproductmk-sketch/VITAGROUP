from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import settings

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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vitagroup-oee-api",
        "environment": settings.environment,
    }
