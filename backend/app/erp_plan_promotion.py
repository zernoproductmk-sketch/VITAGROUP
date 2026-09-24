from __future__ import annotations

import json

from sqlalchemy import text

from .database import engine
from .shifts import ensure_shift


def _resolve_product(connection, article):
    if not article:
        return None

    direct = connection.execute(
        text(
            """
            SELECT id
            FROM products
            WHERE is_active = true
              AND (
                    upper(code) = upper(:code)
                 OR upper(coalesce(article,'')) = upper(:code)
              )
            LIMIT 1
            """
        ),
        {"code": article},
    ).scalar_one_or_none()
    if direct:
        return direct

    external = connection.execute(
        text(
            """
            SELECT product_id
            FROM product_external_codes
            WHERE upper(external_code) = upper(:code)
              AND is_active = true
            ORDER BY
                CASE WHEN source_system = 'COVERSE' THEN 0 ELSE 1 END,
                is_primary DESC
            LIMIT 1
            """
        ),
        {"code": article},
    ).scalar_one_or_none()
    if external:
        return external

    return connection.execute(
        text(
            """
            SELECT entity_id
            FROM external_reference_aliases
            WHERE entity_type = 'PRODUCT'
              AND upper(external_code) = upper(:code)
              AND is_active = true
            LIMIT 1
            """
        ),
        {"code": article},
    ).scalar_one_or_none()


def _resolve_equipment(connection, *codes):
    candidates = [str(code).strip() for code in codes if code and str(code).strip()]
    for code in candidates:
        direct = connection.execute(
            text(
                """
                SELECT id
                FROM equipment
                WHERE is_active = true
                  AND upper(code) = upper(:code)
                LIMIT 1
                """
            ),
            {"code": code},
        ).scalar_one_or_none()
        if direct:
            return direct

        alias = connection.execute(
            text(
                """
                SELECT entity_id
                FROM external_reference_aliases
                WHERE entity_type = 'EQUIPMENT'
                  AND upper(external_code) = upper(:code)
                  AND is_active = true
                ORDER BY
                    CASE
                        WHEN source_system IN ('YANDEX_DISK','ERP') THEN 0
                        WHEN source_system = 'COVERSE' THEN 1
                        ELSE 2
                    END
                LIMIT 1
                """
            ),
            {"code": code},
        ).scalar_one_or_none()
        if alias:
            return alias
    return None


def _upsert_order(connection, row, product_id):
    erp_id = row.get("erp_guid") or None

    existing = connection.execute(
        text(
            """
            SELECT id
            FROM production_orders
            WHERE order_no = :order_no
              AND product_id = :product_id
            LIMIT 1
            """
        ),
        {"order_no": row["order_no"], "product_id": product_id},
    ).scalar_one_or_none()

    if existing:
        connection.execute(
            text(
                """
                UPDATE production_orders
                SET planned_quantity = COALESCE(:planned_quantity, planned_quantity),
                    status = CASE
                        WHEN status = 'CANCELLED' THEN status
                        ELSE 'PLANNED'
                    END,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": existing,
                "planned_quantity": row.get("plan_qty_pcs"),
            },
        )
        return existing

    return connection.execute(
        text(
            """
            INSERT INTO production_orders (
                erp_id,
                order_no,
                product_id,
                planned_quantity,
                status
            ) VALUES (
                :erp_id,
                :order_no,
                :product_id,
                :planned_quantity,
                'PLANNED'
            )
            RETURNING id
            """
        ),
        {
            "erp_id": erp_id,
            "order_no": row["order_no"],
            "product_id": product_id,
            "planned_quantity": row.get("plan_qty_pcs"),
        },
    ).scalar_one()


def _save_order_alias(connection, external_code, order_id):
    if not external_code:
        return
    connection.execute(
        text(
            """
            INSERT INTO external_reference_aliases (
                source_system,
                entity_type,
                external_code,
                entity_id,
                canonical_label
            ) VALUES (
                'ERP',
                'PRODUCTION_ORDER',
                :external_code,
                :entity_id,
                :external_code
            )
            ON CONFLICT (source_system, entity_type, external_code)
            DO UPDATE SET
                entity_id = EXCLUDED.entity_id,
                is_active = true,
                updated_at = now()
            """
        ),
        {
            "external_code": str(external_code).strip(),
            "entity_id": order_id,
        },
    )


def _fallback_norm(connection, product_id, equipment_id, business_date):
    if not product_id or not equipment_id or not business_date:
        return None

    return connection.execute(
        text(
            """
            SELECT ideal_rate_per_hour
            FROM production_norms
            WHERE product_id = :product_id
              AND equipment_id = :equipment_id
              AND operation_id IS NULL
              AND valid_from <= :business_date
              AND (valid_to IS NULL OR valid_to >= :business_date)
            ORDER BY
                CASE
                    WHEN source_system IN ('ERP','1C') THEN 0
                    WHEN source_system = 'COVERSE' THEN 1
                    WHEN source_system = 'WEB' THEN 2
                    ELSE 3
                END,
                valid_from DESC,
                created_at DESC
            LIMIT 1
            """
        ),
        {
            "product_id": product_id,
            "equipment_id": equipment_id,
            "business_date": business_date,
        },
    ).scalar_one_or_none()


def _ensure_run(connection, row, order_id, product_id, equipment_id, shift_id):
    existing = connection.execute(
        text(
            """
            SELECT id
            FROM production_runs
            WHERE production_order_id = :order_id
              AND shift_id = :shift_id
              AND equipment_id = :equipment_id
              AND product_id = :product_id
              AND status <> 'CANCELLED'
            ORDER BY created_at
            LIMIT 1
            """
        ),
        {
            "order_id": order_id,
            "shift_id": shift_id,
            "equipment_id": equipment_id,
            "product_id": product_id,
        },
    ).scalar_one_or_none()
    if existing:
        return existing

    shift = connection.execute(
        text(
            """
            SELECT started_at, ended_at
            FROM shifts
            WHERE id = :shift_id
            """
        ),
        {"shift_id": shift_id},
    ).mappings().first()

    ideal_rate = row.get("ideal_rate_per_hour")
    if ideal_rate is None:
        ideal_rate = _fallback_norm(
            connection,
            product_id,
            equipment_id,
            row.get("business_date"),
        )

    return connection.execute(
        text(
            """
            INSERT INTO production_runs (
                shift_id,
                equipment_id,
                product_id,
                production_order_id,
                planned_start_at,
                planned_end_at,
                planned_qty,
                ideal_rate_per_hour,
                status
            ) VALUES (
                :shift_id,
                :equipment_id,
                :product_id,
                :production_order_id,
                :planned_start_at,
                :planned_end_at,
                :planned_qty,
                :ideal_rate_per_hour,
                'PLANNED'
            )
            RETURNING id
            """
        ),
        {
            "shift_id": shift_id,
            "equipment_id": equipment_id,
            "product_id": product_id,
            "production_order_id": order_id,
            "planned_start_at": shift["started_at"] if shift else None,
            "planned_end_at": shift["ended_at"] if shift else None,
            "planned_qty": row.get("plan_qty_pcs"),
            "ideal_rate_per_hour": ideal_rate,
        },
    ).scalar_one()


def promote_erp_plan(limit: int = 1000) -> dict:
    counters = {
        "processed": 0,
        "orders_created_or_updated": 0,
        "runs_created_or_found": 0,
        "partial": 0,
        "errors": 0,
    }

    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM erp_plan_staging
                WHERE row_status IN ('VALID','PARTIAL')
                  AND promotion_status IN ('UNRESOLVED','PARTIAL','ORDER_CREATED','ERROR')
                ORDER BY business_date, source_file_name, source_row
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": limit},
        ).mappings().all()

        for raw in rows:
            row = dict(raw)
            counters["processed"] += 1

            try:
                product_id = row.get("product_id") or _resolve_product(
                    connection,
                    row.get("article"),
                )
                equipment_id = row.get("equipment_id") or _resolve_equipment(
                    connection,
                    row.get("equipment_code"),
                    row.get("route_equipment_hint"),
                    row.get("route_equipment_name"),
                )

                missing = []
                if not row.get("order_no"):
                    missing.append("order_no")
                if not product_id:
                    missing.append("product_id")

                order_id = row.get("production_order_id")
                if not missing:
                    order_id = order_id or _upsert_order(
                        connection,
                        row,
                        product_id,
                    )
                    counters["orders_created_or_updated"] += 1
                    _save_order_alias(connection, row.get("order_no"), order_id)

                shift_id = row.get("shift_id")
                run_id = row.get("production_run_id")

                if row.get("shift_code") and row.get("business_date"):
                    shift_id = shift_id or ensure_shift(
                        connection,
                        row["business_date"],
                        row["shift_code"],
                    )

                if not equipment_id:
                    missing.append("equipment_id")

                if not row.get("shift_code"):
                    missing.append("shift_code")

                if order_id and product_id and equipment_id and shift_id:
                    run_id = run_id or _ensure_run(
                        connection,
                        row,
                        order_id,
                        product_id,
                        equipment_id,
                        shift_id,
                    )
                    counters["runs_created_or_found"] += 1

                if run_id:
                    promotion_status = "RUN_CREATED"
                    promoted_at_sql = "now()"
                elif order_id:
                    promotion_status = "ORDER_CREATED" if not missing else "PARTIAL"
                    promoted_at_sql = "NULL"
                else:
                    promotion_status = "PARTIAL"
                    promoted_at_sql = "NULL"

                if missing:
                    counters["partial"] += 1

                details = {
                    "missing": sorted(set(missing)),
                    "product_resolved": bool(product_id),
                    "equipment_resolved": bool(equipment_id),
                    "shift_resolved": bool(shift_id),
                    "order_resolved": bool(order_id),
                    "run_resolved": bool(run_id),
                }

                connection.execute(
                    text(
                        f"""
                        UPDATE erp_plan_staging
                        SET product_id = :product_id,
                            equipment_id = :equipment_id,
                            shift_id = :shift_id,
                            production_order_id = :production_order_id,
                            production_run_id = :production_run_id,
                            promotion_status = :promotion_status,
                            promotion_details = CAST(:details AS jsonb),
                            promoted_at = {promoted_at_sql},
                            error_message = NULL,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row["id"],
                        "product_id": product_id,
                        "equipment_id": equipment_id,
                        "shift_id": shift_id,
                        "production_order_id": order_id,
                        "production_run_id": run_id,
                        "promotion_status": promotion_status,
                        "details": json.dumps(details, ensure_ascii=False),
                    },
                )

            except Exception as exc:
                counters["errors"] += 1
                connection.execute(
                    text(
                        """
                        UPDATE erp_plan_staging
                        SET promotion_status = 'ERROR',
                            error_message = :message,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row["id"],
                        "message": str(exc)[:2000],
                    },
                )

    return counters


def erp_plan_rows(limit: int = 300) -> list[dict]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    s.id,
                    s.source_file_name,
                    s.source_sheet,
                    s.source_row,
                    s.task_id,
                    s.business_date,
                    s.shift_code,
                    s.workshop,
                    s.equipment_code,
                    s.route_equipment_hint,
                    s.route_equipment_name,
                    s.order_no,
                    s.article,
                    s.product_name,
                    s.tech_card,
                    s.plan_qty_pcs,
                    s.plan_kg,
                    s.output_unit,
                    s.norm_hours,
                    s.ideal_rate_per_hour,
                    s.row_status,
                    s.promotion_status,
                    s.promotion_details,
                    s.error_message,
                    p.name AS resolved_product_name,
                    e.code AS resolved_equipment_code,
                    po.order_no AS resolved_order_no,
                    pr.id AS resolved_run_id
                FROM erp_plan_staging s
                LEFT JOIN products p ON p.id = s.product_id
                LEFT JOIN equipment e ON e.id = s.equipment_id
                LEFT JOIN production_orders po ON po.id = s.production_order_id
                LEFT JOIN production_runs pr ON pr.id = s.production_run_id
                ORDER BY s.business_date DESC NULLS LAST, s.created_at DESC, s.source_row
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


def erp_plan_summary() -> dict:
    with engine.begin() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    count(*) AS total,
                    count(*) FILTER (WHERE promotion_status = 'RUN_CREATED') AS runs,
                    count(*) FILTER (WHERE promotion_status = 'ORDER_CREATED') AS orders_only,
                    count(*) FILTER (WHERE promotion_status = 'PARTIAL') AS partial,
                    count(*) FILTER (WHERE promotion_status = 'ERROR') AS errors
                FROM erp_plan_staging
                """
            )
        ).mappings().first()

        latest = connection.execute(
            text(
                """
                SELECT
                    source_file_name,
                    source_file_modified,
                    source_sheet,
                    status,
                    rows_read,
                    rows_applied,
                    rows_skipped,
                    rows_error,
                    created_at,
                    completed_at
                FROM erp_plan_import_batches
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()

    return {
        "counts": dict(counts) if counts else {
            "total": 0,
            "runs": 0,
            "orders_only": 0,
            "partial": 0,
            "errors": 0,
        },
        "last_import": dict(latest) if latest else None,
    }


def ensure_run_from_plan_for_event(
    connection,
    production_order_id,
    shift_id,
    occurred_at=None,
):
    if not production_order_id or not shift_id:
        return None

    existing = connection.execute(
        text(
            """
            SELECT id
            FROM production_runs
            WHERE production_order_id = :order_id
              AND shift_id = :shift_id
              AND status <> 'CANCELLED'
            ORDER BY created_at
            LIMIT 1
            """
        ),
        {"order_id": production_order_id, "shift_id": shift_id},
    ).scalar_one_or_none()
    if existing:
        return existing

    shift = connection.execute(
        text(
            """
            SELECT business_date
            FROM shifts
            WHERE id = :shift_id
            """
        ),
        {"shift_id": shift_id},
    ).mappings().first()
    if not shift:
        return None

    candidates = connection.execute(
        text(
            """
            SELECT *
            FROM erp_plan_staging
            WHERE production_order_id = :order_id
              AND business_date = :business_date
              AND product_id IS NOT NULL
              AND equipment_id IS NOT NULL
              AND promotion_status IN ('PARTIAL','ORDER_CREATED','RUN_CREATED')
            ORDER BY source_row
            """
        ),
        {
            "order_id": production_order_id,
            "business_date": shift["business_date"],
        },
    ).mappings().all()

    if len(candidates) != 1:
        return None

    row = dict(candidates[0])
    run_id = _ensure_run(
        connection,
        row,
        production_order_id,
        row["product_id"],
        row["equipment_id"],
        shift_id,
    )

    connection.execute(
        text(
            """
            UPDATE erp_plan_staging
            SET shift_id = :shift_id,
                production_run_id = :run_id,
                promotion_status = 'RUN_CREATED',
                promotion_details = jsonb_set(
                    COALESCE(promotion_details, '{}'::jsonb),
                    '{created_from_coverse_shift}',
                    'true'::jsonb,
                    true
                ),
                promoted_at = now(),
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            "shift_id": shift_id,
            "run_id": run_id,
            "id": row["id"],
        },
    )

    return run_id
