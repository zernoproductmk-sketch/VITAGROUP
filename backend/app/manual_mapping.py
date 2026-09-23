from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text

from .database import engine
from .resolver import resolve_staging_events


FIELD_MAP = {
    "employee_id": {
        "entity_type": "EMPLOYEE",
        "external_field": "personnel_number",
        "label": "Сотрудник",
    },
    "equipment_id": {
        "entity_type": "EQUIPMENT",
        "external_field": "equipment_code",
        "label": "Оборудование",
    },
    "product_id": {
        "entity_type": "PRODUCT",
        "external_field": "article_code",
        "label": "Номенклатура",
    },
    "production_order_id": {
        "entity_type": "PRODUCTION_ORDER",
        "external_field": "order_no",
        "label": "Заказ ERP",
    },
}


def _entity_exists(connection, entity_type: str, entity_id: UUID) -> bool:
    table_by_type = {
        "EMPLOYEE": "employees",
        "EQUIPMENT": "equipment",
        "PRODUCT": "products",
        "PRODUCTION_ORDER": "production_orders",
    }
    table = table_by_type[entity_type]
    return bool(
        connection.execute(
            text(f"SELECT 1 FROM {table} WHERE id = :id LIMIT 1"),
            {"id": entity_id},
        ).scalar_one_or_none()
    )


def manual_map_event(
    staging_event_id: UUID,
    field_name: str,
    entity_id: UUID,
    canonical_label: str | None = None,
) -> dict:
    if field_name not in FIELD_MAP:
        raise ValueError(
            "Ручное сопоставление доступно только для сотрудника, "
            "оборудования, номенклатуры и заказа ERP"
        )

    config = FIELD_MAP[field_name]

    with engine.begin() as connection:
        event = connection.execute(
            text(
                """
                SELECT *
                FROM external_event_staging
                WHERE id = :id
                FOR UPDATE
                """
            ),
            {"id": staging_event_id},
        ).mappings().first()

        if not event:
            raise LookupError("Строка staging не найдена")

        external_code = event.get(config["external_field"])
        if external_code is None or str(external_code).strip() == "":
            raise ValueError(
                f"В строке нет внешнего значения для поля {config['label']}"
            )

        if not _entity_exists(connection, config["entity_type"], entity_id):
            raise LookupError("Выбранный объект справочника не найден")

        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system,
                    entity_type,
                    external_code,
                    entity_id,
                    canonical_label,
                    is_active
                ) VALUES (
                    'COVERSE',
                    :entity_type,
                    :external_code,
                    :entity_id,
                    :canonical_label,
                    true
                )
                ON CONFLICT (source_system, entity_type, external_code)
                DO UPDATE SET
                    entity_id = EXCLUDED.entity_id,
                    canonical_label = EXCLUDED.canonical_label,
                    is_active = true,
                    updated_at = now()
                """
            ),
            {
                "entity_type": config["entity_type"],
                "external_code": str(external_code).strip(),
                "entity_id": entity_id,
                "canonical_label": canonical_label,
            },
        )

        connection.execute(
            text(
                """
                UPDATE external_event_staging
                SET resolution_status = 'UNRESOLVED',
                    processing_status = 'PENDING',
                    error_message = NULL,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": staging_event_id},
        )

        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    table_name,
                    record_id,
                    action,
                    old_data,
                    new_data,
                    reason
                ) VALUES (
                    'external_event_staging',
                    :record_id,
                    'UPDATE',
                    CAST(:old_data AS jsonb),
                    CAST(:new_data AS jsonb),
                    :reason
                )
                """
            ),
            {
                "record_id": staging_event_id,
                "old_data": json.dumps(
                    {
                        "field_name": field_name,
                        "external_code": external_code,
                        "resolution_status": event.get("resolution_status"),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                "new_data": json.dumps(
                    {
                        "field_name": field_name,
                        "external_code": external_code,
                        "entity_id": str(entity_id),
                        "entity_type": config["entity_type"],
                    },
                    ensure_ascii=False,
                ),
                "reason": "Ручное сопоставление внешнего кода Coverse",
            },
        )

    resolution = resolve_staging_events(limit=500)

    with engine.begin() as connection:
        updated = connection.execute(
            text(
                """
                SELECT
                    id,
                    event_type,
                    resolution_status,
                    resolution_details,
                    employee_id,
                    equipment_id,
                    product_id,
                    production_order_id,
                    production_run_id,
                    shift_id
                FROM external_event_staging
                WHERE id = :id
                """
            ),
            {"id": staging_event_id},
        ).mappings().first()

    return {
        "status": "ok",
        "field_name": field_name,
        "entity_type": config["entity_type"],
        "external_code": str(external_code).strip(),
        "resolution_batch": resolution,
        "event": dict(updated) if updated else None,
    }
