from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_roles
from .database import latest_staged_events, stage_external_events
from .integrations.coverse import CoverseClient, SOURCES
from .normalization import normalize_coverse_event

router = APIRouter(
    prefix="/api/v1/integrations/coverse",
    tags=["Coverse"],
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


@router.get("/sources")
def sources():
    return [
        {
            "key": item.key,
            "document_id": item.document_id,
            "sheet": item.sheet_name,
            "range": item.range_a1,
            "mapped_fields": list(item.columns.keys()),
            "mapping_ready": bool(item.columns),
        }
        for item in SOURCES.values()
    ]


@router.get("/preview/{source_key}")
async def preview(source_key: str):
    source = SOURCES.get(source_key)
    if source is None:
        raise HTTPException(status_code=404, detail="Unknown Coverse source")

    client = CoverseClient()
    try:
        rows = await client.read_source(source_key)
        normalized = [
            normalize_coverse_event(source_key, row, source.date_is_business_date)
            for row in rows
        ]
        return {
            "source": source_key,
            "count": len(normalized),
            "rows": normalized[:100],
        }
    finally:
        await client.close()


@router.post("/sync/{source_key}")
async def sync(source_key: str):
    source = SOURCES.get(source_key)
    if source is None:
        raise HTTPException(status_code=404, detail="Unknown Coverse source")

    client = CoverseClient()
    try:
        rows = await client.read_source(source_key)
        events = [
            normalize_coverse_event(source_key, row, source.date_is_business_date)
            for row in rows
        ]
        result = stage_external_events(events)
        return {"source": source_key, **result}
    finally:
        await client.close()


@router.get("/staging/{source_key}")
def staging(source_key: str, limit: int = Query(default=100, ge=1, le=500)):
    if source_key not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown Coverse source")
    return {
        "source": source_key,
        "rows": latest_staged_events(source_key, limit),
    }
