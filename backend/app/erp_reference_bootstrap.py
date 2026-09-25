from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from .database import engine
from .normalization import normalized_code


def _candidate_rows(connection, limit: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT
                id,
                source_file_name,
                source_sheet,
                source_row,
                business_date,
                shift_code,
                article,
                product_name,
                route_equipment_hint,
                route_equipment_name,
                ideal_rate_per_hour,
                row_status,
                promotion_status
            FROM erp_plan_staging
            WHERE row_status IN ('VALID','PARTIAL')
              AND promotion_status IN ('UNRESOLVED','PARTIAL','ORDER_CREATED','ERROR')
            ORDER BY business_date DESC NULLS LAST, created_at DESC, source_row
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


def _product_exists(connection, article: str | None):
    if not article:
        return None
    return connection.execute(
        text(
            """
            SELECT id, code, article, name
            FROM products
            WHERE is_active = true
              AND (
                    upper(code) = upper(:article)
                 OR upper(coalesce(article,'')) = upper(:article)
              )
            LIMIT 1
            """
        ),
        {"article": article},
    ).mappings().first()


def _equipment_exists(connection, code: str | None):
    if not code:
        return None
    return connection.execute(
        text(
            """
            SELECT id, code, name
            FROM equipment
            WHERE is_active = true
              AND upper(code) = upper(:code)
            LIMIT 1
            """
        ),
        {"code": code},
    ).mappings().first()


def preview_erp_reference_bootstrap(limit: int = 100) -> dict[str, Any]:
    with engine.begin() as connection:
        rows = _candidate_rows(connection, limit)
        items: list[dict[str, Any]] = []

        for row in rows:
            article = str(row.get("article") or "").strip() or None
            equipment_code = normalized_code(row.get("route_equipment_hint"))

            product = _product_exists(connection, article)
            equipment = _equipment_exists(connection, equipment_code)

            items.append(
                {
                    "staging_id": str(row["id"]),
                    "business_date": row.get("business_date"),
                    "shift_code": row.get("shift_code"),
                    "article": article,
                    "product_name": row.get("product_name"),
                    "product_action": "EXISTS" if product else "CREATE",
                    "equipment_code": equipment_code,
                    "equipment_name": row.get("route_equipment_name"),
                    "equipment_action": "EXISTS" if equipment else "CREATE",
                    "ideal_rate_per_hour": row.get("ideal_rate_per_hour"),
                    "norm_action": (
                        "UPSERT"
                        if row.get("ideal_rate_per_hour")
                        and article
                        and equipment_code
                        else "SKIP"
                    ),
                }
            )

    return {
        "mode": "PREVIEW",
        "rows": len(items),
        "items": items,
    }


def _ensure_product(connection, *, article: str, name: str | None):
    product_id = connection.execute(
        text(
            """
            INSERT INTO products (
                code, article, name, unit, is_active
            ) VALUES (
                :article, :article, :name, 'pcs', true
            )
            ON CONFLICT (code) DO UPDATE SET
                article = COALESCE(products.article, EXCLUDED.article),
                name = CASE
                    WHEN products.name IS NULL OR btrim(products.name) = ''
                    THEN EXCLUDED.name
                    ELSE products.name
                END,
                is_active = true,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "article": article,
            "name": (name or article).strip(),
        },
    ).scalar_one()

    connection.execute(
        text(
            """
            INSERT INTO product_external_codes (
                product_id, source_system, code_type, external_code,
                is_primary, metadata
            ) VALUES (
                :product_id, 'ERP', 'ARTICLE', :article, true,
                '{"bootstrap":"erp_plan"}'::jsonb
            )
            ON CONFLICT (source_system, code_type, external_code)
            DO UPDATE SET
                product_id = EXCLUDED.product_id,
                is_primary = true,
                is_active = true,
                updated_at = now()
            """
        ),
        {"product_id": product_id, "article": normalized_code(article)},
    )

    connection.execute(
        text(
            """
            INSERT INTO external_reference_aliases (
                source_system, entity_type, external_code,
                entity_id, canonical_label
            ) VALUES (
                'ERP', 'PRODUCT', :article, :product_id, :article
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
            "article": normalized_code(article),
            "product_id": product_id,
        },
    )
    return product_id


def _ensure_equipment(connection, *, code: str, name: str | None):
    equipment_id = connection.execute(
        text(
            """
            INSERT INTO equipment (code, name, is_active)
            VALUES (:code, :name, true)
            ON CONFLICT (code) DO UPDATE SET
                name = CASE
                    WHEN equipment.name IS NULL OR btrim(equipment.name) = ''
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
            "name": (name or code).strip(),
        },
    ).scalar_one()

    for alias in {code, normalized_code(name) if name else None}:
        if not alias:
            continue
        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system, entity_type, external_code,
                    entity_id, canonical_label
                ) VALUES (
                    'ERP', 'EQUIPMENT', :alias, :equipment_id, :code
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
                "alias": alias,
                "equipment_id": equipment_id,
                "code": code,
            },
        )
    return equipment_id


def _upsert_norm(
    connection,
    *,
    product_id,
    equipment_id,
    business_date,
    rate: Decimal,
    staging_id,
):
    source_record_id = f"erp_plan_staging:{staging_id}"
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
                    valid_from = :business_date,
                    valid_to = NULL
                WHERE id = :id
                """
            ),
            {
                "id": existing,
                "product_id": product_id,
                "equipment_id": equipment_id,
                "rate": rate,
                "business_date": business_date,
            },
        )
        return existing, "UPDATED"

    norm_id = connection.execute(
        text(
            """
            INSERT INTO production_norms (
                product_id, equipment_id, operation_id,
                ideal_rate_per_hour, valid_from, valid_to,
                source_system, source_record_id
            ) VALUES (
                :product_id, :equipment_id, NULL,
                :rate, :business_date, NULL,
                'ERP', :source_record_id
            )
            RETURNING id
            """
        ),
        {
            "product_id": product_id,
            "equipment_id": equipment_id,
            "rate": rate,
            "business_date": business_date,
            "source_record_id": source_record_id,
        },
    ).scalar_one()
    return norm_id, "CREATED"


def apply_erp_reference_bootstrap(limit: int = 100) -> dict[str, Any]:
    counters = {
        "rows": 0,
        "products_created_or_found": 0,
        "equipment_created_or_found": 0,
        "norms_created_or_updated": 0,
        "skipped": 0,
    }
    results: list[dict[str, Any]] = []

    with engine.begin() as connection:
        rows = _candidate_rows(connection, limit)

        for row in rows:
            counters["rows"] += 1
            article = str(row.get("article") or "").strip()
            equipment_code = normalized_code(row.get("route_equipment_hint"))
            product_name = str(row.get("product_name") or "").strip() or article
            equipment_name = str(row.get("route_equipment_name") or "").strip() or equipment_code
            rate = row.get("ideal_rate_per_hour")
            business_date = row.get("business_date")

            missing = []
            if not article:
                missing.append("article")
            if not equipment_code:
                missing.append("equipment_code")

            if missing:
                counters["skipped"] += 1
                results.append(
                    {
                        "staging_id": str(row["id"]),
                        "status": "SKIPPED",
                        "missing": missing,
                    }
                )
                continue

            product_id = _ensure_product(
                connection,
                article=article,
                name=product_name,
            )
            counters["products_created_or_found"] += 1

            equipment_id = _ensure_equipment(
                connection,
                code=equipment_code,
                name=equipment_name,
            )
            counters["equipment_created_or_found"] += 1

            norm_status = None
            if rate is not None and business_date is not None:
                _, norm_status = _upsert_norm(
                    connection,
                    product_id=product_id,
                    equipment_id=equipment_id,
                    business_date=business_date,
                    rate=rate,
                    staging_id=row["id"],
                )
                counters["norms_created_or_updated"] += 1

            connection.execute(
                text(
                    """
                    UPDATE erp_plan_staging
                    SET product_id = :product_id,
                        equipment_id = :equipment_id,
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

            results.append(
                {
                    "staging_id": str(row["id"]),
                    "status": "APPLIED",
                    "article": article,
                    "equipment_code": equipment_code,
                    "norm_status": norm_status,
                }
            )

    return {
        "mode": "APPLY",
        **counters,
        "items": results,
    }
