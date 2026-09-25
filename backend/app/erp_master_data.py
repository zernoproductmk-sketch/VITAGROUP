from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from .database import engine
from .normalization import normalized_code


def _unit(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"шт", "pcs", "piece", "pieces"}:
        return "pcs"
    if raw in {"кг", "kg"}:
        return "kg"
    return raw or "pcs"


def _equipment_code(row: dict[str, Any]) -> str | None:
    return normalized_code(
        row.get("route_equipment_hint")
        or row.get("equipment_code")
    )


def _product_id(connection, article: str | None):
    if not article:
        return None
    return connection.execute(
        text(
            """
            SELECT id
            FROM products
            WHERE upper(code) = upper(:article)
               OR upper(coalesce(article, '')) = upper(:article)
            ORDER BY is_active DESC, updated_at DESC
            LIMIT 1
            """
        ),
        {"article": article},
    ).scalar_one_or_none()


def _equipment_id(connection, code: str | None, full_name: str | None):
    candidates = [
        item
        for item in (code, normalized_code(full_name))
        if item
    ]
    for candidate in candidates:
        direct = connection.execute(
            text(
                """
                SELECT id
                FROM equipment
                WHERE upper(code) = upper(:candidate)
                   OR upper(name) = upper(:candidate)
                ORDER BY is_active DESC, updated_at DESC
                LIMIT 1
                """
            ),
            {"candidate": candidate},
        ).scalar_one_or_none()
        if direct:
            return direct

        alias = connection.execute(
            text(
                """
                SELECT entity_id
                FROM external_reference_aliases
                WHERE entity_type = 'EQUIPMENT'
                  AND upper(external_code) = upper(:candidate)
                  AND is_active = true
                ORDER BY
                    CASE WHEN source_system = 'ERP' THEN 0 ELSE 1 END,
                    updated_at DESC
                LIMIT 1
                """
            ),
            {"candidate": candidate},
        ).scalar_one_or_none()
        if alias:
            return alias
    return None


def _rows(connection, limit: int) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            """
            SELECT *
            FROM erp_plan_staging
            WHERE row_status IN ('VALID', 'PARTIAL')
              AND promotion_status IN ('UNRESOLVED', 'PARTIAL', 'ORDER_CREATED', 'ERROR')
            ORDER BY business_date DESC NULLS LAST, created_at DESC, source_row
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(item) for item in result]


def preview_erp_master_data(limit: int = 100) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    with engine.begin() as connection:
        for row in _rows(connection, limit):
            article = str(row.get("article") or "").strip() or None
            equipment_code = _equipment_code(row)
            product_id = row.get("product_id") or _product_id(connection, article)
            equipment_id = row.get("equipment_id") or _equipment_id(
                connection,
                equipment_code,
                row.get("route_equipment_name"),
            )
            items.append(
                {
                    "staging_id": str(row["id"]),
                    "business_date": row.get("business_date"),
                    "shift_code": row.get("shift_code"),
                    "order_no": row.get("order_no"),
                    "article": article,
                    "product_name": row.get("product_name"),
                    "equipment_code": equipment_code,
                    "equipment_name": row.get("route_equipment_name"),
                    "ideal_rate_per_hour": row.get("ideal_rate_per_hour"),
                    "will_create_product": bool(article and not product_id),
                    "will_create_equipment": bool(equipment_code and not equipment_id),
                    "will_upsert_erp_norm": bool(
                        row.get("ideal_rate_per_hour")
                        and Decimal(str(row.get("ideal_rate_per_hour"))) > 0
                    ),
                    "blocked": [
                        name
                        for name, value in (
                            ("article", article),
                            ("equipment_code", equipment_code),
                        )
                        if not value
                    ],
                }
            )

    return {
        "status": "PREVIEW",
        "rows": len(items),
        "items": items,
    }


def _upsert_product(connection, row: dict[str, Any]):
    article = str(row.get("article") or "").strip()
    if not article:
        return None, False

    existing = row.get("product_id") or _product_id(connection, article)
    if existing:
        return existing, False

    product_id = connection.execute(
        text(
            """
            INSERT INTO products (code, article, name, unit, is_active)
            VALUES (:code, :article, :name, :unit, true)
            ON CONFLICT (code) DO UPDATE SET
                article = COALESCE(products.article, EXCLUDED.article),
                name = CASE
                    WHEN products.name IS NULL OR products.name = products.code
                    THEN EXCLUDED.name
                    ELSE products.name
                END,
                is_active = true,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "code": article,
            "article": article,
            "name": str(row.get("product_name") or article).strip(),
            "unit": _unit(row.get("output_unit")),
        },
    ).scalar_one()

    for source_system, code_type, external_code, primary in (
        ("ERP", "ARTICLE", article, True),
    ):
        connection.execute(
            text(
                """
                INSERT INTO product_external_codes (
                    product_id, source_system, code_type, external_code,
                    is_primary, metadata
                ) VALUES (
                    :product_id, :source_system, :code_type, :external_code,
                    :is_primary, '{"source":"ERP plan bootstrap"}'::jsonb
                )
                ON CONFLICT (source_system, code_type, external_code)
                DO UPDATE SET
                    product_id = EXCLUDED.product_id,
                    is_active = true,
                    updated_at = now()
                """
            ),
            {
                "product_id": product_id,
                "source_system": source_system,
                "code_type": code_type,
                "external_code": normalized_code(external_code),
                "is_primary": primary,
            },
        )

    connection.execute(
        text(
            """
            INSERT INTO external_reference_aliases (
                source_system, entity_type, external_code, entity_id,
                canonical_label, metadata
            ) VALUES (
                'ERP', 'PRODUCT', :external_code, :entity_id,
                :canonical_label, '{"source":"ERP plan bootstrap"}'::jsonb
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
            "external_code": normalized_code(article),
            "entity_id": product_id,
            "canonical_label": article,
        },
    )

    return product_id, True


def _upsert_equipment(connection, row: dict[str, Any]):
    code = _equipment_code(row)
    full_name = str(row.get("route_equipment_name") or "").strip() or None
    if not code:
        return None, False

    existing = row.get("equipment_id") or _equipment_id(
        connection,
        code,
        full_name,
    )
    if existing:
        return existing, False

    equipment_id = connection.execute(
        text(
            """
            INSERT INTO equipment (code, name, is_active)
            VALUES (:code, :name, true)
            ON CONFLICT (code) DO UPDATE SET
                name = CASE
                    WHEN equipment.name IS NULL OR equipment.name = equipment.code
                    THEN EXCLUDED.name
                    ELSE equipment.name
                END,
                is_active = true,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "code": code,
            "name": full_name or code,
        },
    ).scalar_one()

    aliases = {
        normalized_code(code),
        normalized_code(row.get("equipment_code")),
        normalized_code(row.get("route_equipment_hint")),
        normalized_code(full_name),
    }
    for alias in {item for item in aliases if item}:
        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system, entity_type, external_code, entity_id,
                    canonical_label, metadata
                ) VALUES (
                    'ERP', 'EQUIPMENT', :external_code, :entity_id,
                    :canonical_label, '{"source":"ERP plan bootstrap"}'::jsonb
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
                "external_code": alias,
                "entity_id": equipment_id,
                "canonical_label": code,
            },
        )

    return equipment_id, True


def _upsert_norm(
    connection,
    row: dict[str, Any],
    product_id,
    equipment_id,
) -> bool:
    rate = row.get("ideal_rate_per_hour")
    business_date = row.get("business_date")
    if not product_id or not equipment_id or not business_date or rate is None:
        return False
    if Decimal(str(rate)) <= 0:
        return False

    source_record_id = f"ERP_PLAN:{row['id']}"
    existing = connection.execute(
        text(
            """
            SELECT id
            FROM production_norms
            WHERE source_system = 'ERP'
              AND source_record_id = :source_record_id
            LIMIT 1
            """
        ),
        {"source_record_id": source_record_id},
    ).scalar_one_or_none()

    if existing:
        connection.execute(
            text(
                """
                UPDATE production_norms
                SET product_id = :product_id,
                    equipment_id = :equipment_id,
                    ideal_rate_per_hour = :rate,
                    valid_from = :valid_from
                WHERE id = :id
                """
            ),
            {
                "id": existing,
                "product_id": product_id,
                "equipment_id": equipment_id,
                "rate": rate,
                "valid_from": business_date,
            },
        )
        return True

    connection.execute(
        text(
            """
            INSERT INTO production_norms (
                product_id, equipment_id, operation_id,
                ideal_rate_per_hour, valid_from,
                source_system, source_record_id
            ) VALUES (
                :product_id, :equipment_id, NULL,
                :rate, :valid_from,
                'ERP', :source_record_id
            )
            """
        ),
        {
            "product_id": product_id,
            "equipment_id": equipment_id,
            "rate": rate,
            "valid_from": business_date,
            "source_record_id": source_record_id,
        },
    )
    return True


def apply_erp_master_data(limit: int = 100) -> dict[str, Any]:
    counters = {
        "processed": 0,
        "products_created": 0,
        "equipment_created": 0,
        "erp_norms_upserted": 0,
        "rows_linked": 0,
        "blocked": 0,
    }

    with engine.begin() as connection:
        for row in _rows(connection, limit):
            counters["processed"] += 1

            product_id, product_created = _upsert_product(connection, row)
            equipment_id, equipment_created = _upsert_equipment(connection, row)

            if product_created:
                counters["products_created"] += 1
            if equipment_created:
                counters["equipment_created"] += 1

            if not product_id or not equipment_id:
                counters["blocked"] += 1
                continue

            if _upsert_norm(connection, row, product_id, equipment_id):
                counters["erp_norms_upserted"] += 1

            connection.execute(
                text(
                    """
                    UPDATE erp_plan_staging
                    SET product_id = :product_id,
                        equipment_id = :equipment_id,
                        promotion_status = CASE
                            WHEN promotion_status = 'ERROR' THEN 'UNRESOLVED'
                            ELSE promotion_status
                        END,
                        error_message = NULL,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "id": row["id"],
                    "product_id": product_id,
                    "equipment_id": equipment_id,
                },
            )
            counters["rows_linked"] += 1

    return {
        "status": "APPLIED",
        **counters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap minimal product/equipment master data from ERP plan staging."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    result = (
        apply_erp_master_data(args.limit)
        if args.apply
        else preview_erp_master_data(args.limit)
    )
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
