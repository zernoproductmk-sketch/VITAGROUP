from fastapi import APIRouter, HTTPException

from .integrations.coverse import CoverseClient, SOURCES

router = APIRouter(prefix="/api/v1/integrations/coverse", tags=["Coverse"])


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
    if source_key not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown Coverse source")

    client = CoverseClient()
    try:
        rows = await client.read_source(source_key)
        return {
            "source": source_key,
            "count": len(rows),
            "rows": rows[:100],
        }
    finally:
        await client.close()
