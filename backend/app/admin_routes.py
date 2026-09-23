from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .integration_status import integration_dashboard, reference_candidates
from .manual_mapping import FIELD_MAP, manual_map_event
from .promotion import promote_resolved_events
from .resolver import add_alias, resolve_staging_events, unresolved_events

router = APIRouter(prefix="/api/v1/reference", tags=["Reference resolution"])


class AliasInput(BaseModel):
    source_system: str = "COVERSE"
    entity_type: str = Field(pattern="^(EMPLOYEE|EQUIPMENT|PRODUCT|PRODUCTION_ORDER)$")
    external_code: str
    entity_id: UUID
    canonical_label: str | None = None


class ManualMapInput(BaseModel):
    staging_event_id: UUID
    field_name: str = Field(
        pattern="^(employee_id|equipment_id|product_id|production_order_id)$"
    )
    entity_id: UUID
    canonical_label: str | None = None


@router.get("/dashboard")
def dashboard():
    return integration_dashboard()


@router.get("/manual-fields")
def manual_fields():
    return [
        {
            "field_name": field_name,
            "entity_type": config["entity_type"],
            "external_field": config["external_field"],
            "label": config["label"],
        }
        for field_name, config in FIELD_MAP.items()
    ]


@router.get("/candidates/{entity_type}")
def candidates(
    entity_type: str,
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
):
    allowed = {"EMPLOYEE", "EQUIPMENT", "PRODUCT", "PRODUCTION_ORDER"}
    if entity_type not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported entity type")
    return {
        "entity_type": entity_type,
        "rows": reference_candidates(entity_type, q, limit),
    }


@router.post("/manual-map")
def manual_map(payload: ManualMapInput):
    try:
        return manual_map_event(
            staging_event_id=payload.staging_event_id,
            field_name=payload.field_name,
            entity_id=payload.entity_id,
            canonical_label=payload.canonical_label,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
