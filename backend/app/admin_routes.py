from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .promotion import promote_resolved_events
from .resolver import add_alias, resolve_staging_events, unresolved_events

router = APIRouter(prefix="/api/v1/reference", tags=["Reference resolution"])


class AliasInput(BaseModel):
    source_system: str = "COVERSE"
    entity_type: str = Field(pattern="^(EMPLOYEE|EQUIPMENT|PRODUCT|PRODUCTION_ORDER)$")
    external_code: str
    entity_id: UUID
    canonical_label: str | None = None


@router.post("/resolve")
def resolve(limit: int = Query(default=500, ge=1, le=5000)):
    return resolve_staging_events(limit)


@router.get("/unresolved")
def unresolved(limit: int = Query(default=200, ge=1, le=1000)):
    return {"rows": unresolved_events(limit)}


@router.post("/aliases")
def alias(payload: AliasInput):
    add_alias(
        source_system=payload.source_system,
        entity_type=payload.entity_type,
        external_code=payload.external_code,
        entity_id=payload.entity_id,
        canonical_label=payload.canonical_label,
    )
    return {"status": "ok"}


@router.post("/promote")
def promote(limit: int = Query(default=500, ge=1, le=5000)):
    return promote_resolved_events(limit)
