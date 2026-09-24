from fastapi import APIRouter, Depends, HTTPException

from .auth import require_roles
from .master_data_sync import preview_reference, sync_all_references, sync_reference
from .reference_sources import REFERENCE_SOURCES

router = APIRouter(
    prefix="/api/v1/master-data",
    tags=["Master data"],
    dependencies=[
        Depends(
            require_roles(
                "ACCOUNTANT_PRODUCTION",
                "ECONOMIST",
                "ADMIN",
            )
        )
    ],
)


@router.get("/sources")
def sources():
    return [
        {
            "key": source.key,
            "document_id": source.document_id,
            "sheet": source.sheet_name,
            "range": source.range_a1,
            "required_headers": source.required_headers,
        }
        for source in REFERENCE_SOURCES.values()
    ]


@router.post("/sync")
async def sync_all():
    return await sync_all_references()


@router.post("/sync/{source_key}")
async def sync_one(source_key: str):
    if source_key not in REFERENCE_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown reference source")
    return await sync_reference(source_key)


@router.post("/preview/{source_key}")
async def preview_one(source_key: str):
    if source_key not in REFERENCE_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown reference source")
    return await preview_reference(source_key)
