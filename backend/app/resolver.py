from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .database import engine
from .erp_plan_promotion import ensure_run_from_plan_for_event
from .shifts import ensure_shift


REQUIRED_BY_EVENT: dict[str, set[str]] = {
    "downtime": {"employee_id", "equipment_id", "shift_id"},
    "production_output": {"employee_id", "production_order_id", "production_run_id", "equipment_id", "product_id", "shift_id"},
    "qc_defects": {"employee_id", "production_run_id", "product_id", "shift_id"},
    "warehouse": {"employee_id", "product_id", "shift_id"},
    "accountant": {"employee_id", "equipment_id", "product_id", "shift_id"},
}


def _one(connection, sql: str, params: dict) -> Any:
    return connection.execute(text(sql), params).scalar_one_or_none()


def _resolve_alias(connection, entity_type: str, external_code: str | None):
    if not external_code:
        return None
    return _one(
        connection,
        """
        SELECT entity_id
        FROM external_reference_aliases
        WHERE source_system = 'COVERSE'
          AND entity_type = :entity_type
          AND upper(external_code) = upper(:external_code)
          AND is_active = true
        """,
        {"entity_type": entity_type, "external_code": external_code},
    )


def _find_shift(connection, business_date, shift_code):
    return ensure_shift(connection, business_date, shift_code)


def _find_employee(connection, personnel_number):
    if not personnel_number:
        return None
    direct = _one(
        connection,
        "SELECT id FROM employees WHERE personnel_number = :code AND is_active = true LIMIT 1",
        {"code": personnel_number},
    )
    return direct or _resolve_alias(connection, "EMPLOYEE", personnel_number)


def _find_equipment(connection, equipment_code):
    if not equipment_code:
        return None
    direct = _one(
        connection,
        "SELECT id FROM equipment WHERE upper(code) = upper(:code) AND is_active = true LIMIT 1",
        {"code": equipment_code},
    )
    return direct or _resolve_alias(connection, "EQUIPMENT", equipment_code)


def _find_product(connection, article_code):
    if not article_code:
        return None
    direct = _one(
        connection,
        """
        SELECT id
        FROM products
        WHERE is_active = true
          AND (upper(code) = upper(:code) OR upper(coalesce(article,'')) = upper(:code))
        LIMIT 1
        """,
        {"code": article_code},
    )
    if direct:
        return direct

    external = _one(
        connection,
        """
        SELECT product_id
        FROM product_external_codes
        WHERE source_system = 'COVERSE'
          AND upper(external_code) = upper(:code)
          AND is_active = true
        LIMIT 1
        """,
        {"code": article_code},
    )
    return external or _resolve_alias(connection, "PRODUCT", article_code)


def _find_order(connection, order_no):
    if not order_no:
        return None
    direct = _one(
        connection,
        """
        SELECT id
        FROM production_orders
        WHERE upper(order_no) = upper(:code)
           OR upper(coalesce(erp_id,'')) = upper(:code)
        LIMIT 1
        """,
        {"code": order_no},
    )
    return direct or _resolve_alias(connection, "PRODUCTION_ORDER", order_no)


def _find_run_for_order(connection, production_order_id, shift_id, occurred_at):
    if not production_order_id:
        return None
    return _one(
        connection,
        """
        SELECT pr.id
        FROM production_runs pr
        WHERE pr.production_order_id = :order_id
          AND (:shift_id IS NULL OR pr.shift_id = :shift_id)
          AND pr.status <> 'CANCELLED'
          AND (
                :occurred_at IS NULL
                OR pr.actual_start_at IS NULL
                OR pr.actual_start_at <= :occurred_at
              )
          AND (
                :occurred_at IS NULL
                OR pr.actual_end_at IS NULL
                OR pr.actual_end_at >= :occurred_at
              )
        ORDER BY
          CASE WHEN pr.shift_id = :shift_id THEN 0 ELSE 1 END,
          pr.actual_start_at NULLS LAST
        LIMIT 1
        """,
        {"order_id": production_order_id, "shift_id": shift_id, "occurred_at": occurred_at},
    )


def _find_run_for_dimensions(connection, shift_id, equipment_id, product_id, occurred_at):
    if not shift_id:
        return None

    conditions = [
        "pr.shift_id = :shift_id",
        "pr.status <> 'CANCELLED'",
    ]
    params = {"shift_id": shift_id}

    if equipment_id:
        conditions.append("pr.equipment_id = :equipment_id")
        params["equipment_id"] = equipment_id

    if product_id:
        conditions.append("pr.product_id = :product_id")
        params["product_id"] = product_id

    if occurred_at:
        conditions.extend(
            [
                "(pr.actual_start_at IS NULL OR pr.actual_start_at <= :occurred_at)",
                "(pr.actual_end_at IS NULL OR pr.actual_end_at >= :occurred_at)",
            ]
        )
        params["occurred_at"] = occurred_at

    sql = f"""
        SELECT pr.id
        FROM production_runs pr
        WHERE {' AND '.join(conditions)}
        ORDER BY pr.actual_start_at NULLS LAST
        LIMIT 1
    """
    return _one(connection, sql, params)


def _inherit_from_run(connection, run_id):
    if not run_id:
        return {}
    row = connection.execute(
        text(
            """
            SELECT shift_id, equipment_id, product_id, production_order_id
            FROM production_runs
            WHERE id = :id
            """
        ),
        {"id": run_id},
    ).mappings().first()
    return dict(row) if row else {}


def _link_by_ticket(connection, current_id, ticket_no, event_type):
    if not ticket_no:
        return None
    counterpart = "accountant" if event_type == "warehouse" else "warehouse" if event_type == "accountant" else None
    if counterpart is None:
        return None
    return _one(
        connection,
        """
        SELECT id
        FROM external_event_staging
        WHERE event_type = :counterpart
          AND ticket_no = :ticket_no
          AND id <> :current_id
        ORDER BY response_at DESC NULLS LAST
        LIMIT 1
        """,
        {"counterpart": counterpart, "ticket_no": ticket_no, "current_id": current_id},
    )


def _inherit_linked_dimensions(connection, linked_id):
    if not linked_id:
        return {}
    row = connection.execute(
        text(
            """
            SELECT shift_id, employee_id, equipment_id, product_id, production_order_id, production_run_id
            FROM external_event_staging
            WHERE id = :id
            """
        ),
        {"id": linked_id},
    ).mappings().first()
    return dict(row) if row else {}


def _write_issues(connection, event_id, missing: list[str], event: dict):
    connection.execute(
        text("DELETE FROM resolution_issues WHERE staging_event_id = :id AND status = 'OPEN'"),
        {"id": event_id},
    )
    for field in missing:
        external_field = {
            "employee_id": "personnel_number",
            "equipment_id": "equipment_code",
            "product_id": "article_code",
            "production_order_id": "order_no",
            "production_run_id": "production_run",
            "shift_id": "business_date/shift_code",
        }.get(field)
        external_value = event.get(external_field) if external_field else None
        connection.execute(
            text(
                """
                INSERT INTO resolution_issues (
                    staging_event_id, issue_code, field_name, external_value, message
                ) VALUES (
                    :event_id, :issue_code, :field_name, :external_value, :message
                )
                ON CONFLICT (staging_event_id, issue_code, field_name)
                DO UPDATE SET
                    external_value = EXCLUDED.external_value,
                    message = EXCLUDED.message,
                    status = 'OPEN',
                    resolved_at = NULL
                """
            ),
            {
                "event_id": event_id,
                "issue_code": "REFERENCE_NOT_RESOLVED",
                "field_name": field,
                "external_value": None if external_value is None else str(external_value),
                "message": f"Не удалось однозначно определить {field}",
            },
        )


def resolve_staging_events(limit: int = 500) -> dict:
    counters = {"processed": 0, "resolved": 0, "partial": 0, "errors": 0}

    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM external_event_staging
                WHERE processing_status IN ('PENDING','ERROR')
                  AND resolution_status IN ('UNRESOLVED','PARTIAL','ERROR')
                ORDER BY response_at, source_row
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": limit},
        ).mappings().all()

        for raw in rows:
            event = dict(raw)
            counters["processed"] += 1
            savepoint = connection.begin_nested()
            try:
                shift_id = event.get("shift_id") or _find_shift(
                    connection, event.get("business_date"), event.get("shift_code")
                )
                employee_id = event.get("employee_id") or _find_employee(
                    connection, event.get("personnel_number")
                )
                equipment_id = event.get("equipment_id") or _find_equipment(
                    connection, event.get("equipment_code")
                )
                product_id = event.get("product_id") or _find_product(
                    connection, event.get("article_code")
                )
                order_id = event.get("production_order_id") or _find_order(
                    connection, event.get("order_no")
                )

                linked_id = event.get("linked_staging_id") or _link_by_ticket(
                    connection,
                    event["id"],
                    event.get("ticket_no"),
                    event["event_type"],
                )
                linked = _inherit_linked_dimensions(connection, linked_id)
                shift_id = shift_id or linked.get("shift_id")
                equipment_id = equipment_id or linked.get("equipment_id")
                product_id = product_id or linked.get("product_id")
                order_id = order_id or linked.get("production_order_id")
                run_id = event.get("production_run_id") or linked.get("production_run_id")

                if not run_id and order_id:
                    run_id = _find_run_for_order(
                        connection, order_id, shift_id, event.get("occurred_at")
                    )
                if not run_id and order_id and shift_id:
                    run_id = ensure_run_from_plan_for_event(
                        connection,
                        order_id,
                        shift_id,
                        event.get("occurred_at"),
                    )
                if not run_id and event["event_type"] in {"qc_defects","warehouse","accountant"}:
                    run_id = _find_run_for_dimensions(
                        connection,
                        shift_id,
                        equipment_id,
                        product_id,
                        event.get("occurred_at"),
                    )

                inherited = _inherit_from_run(connection, run_id)
                shift_id = shift_id or inherited.get("shift_id")
                equipment_id = equipment_id or inherited.get("equipment_id")
                product_id = product_id or inherited.get("product_id")
                order_id = order_id or inherited.get("production_order_id")

                resolved = {
                    "shift_id": shift_id,
                    "employee_id": employee_id,
                    "equipment_id": equipment_id,
                    "product_id": product_id,
                    "production_order_id": order_id,
                    "production_run_id": run_id,
                }

                required = REQUIRED_BY_EVENT.get(event["event_type"], set())
                missing = sorted(field for field in required if not resolved.get(field))
                if not missing:
                    status = "RESOLVED"
                    counters["resolved"] += 1
                else:
                    status = "PARTIAL"
                    counters["partial"] += 1

                details = {
                    "required": sorted(required),
                    "missing": missing,
                    "linked_by_ticket": str(linked_id) if linked_id else None,
                }

                connection.execute(
                    text(
                        """
                        UPDATE external_event_staging
                        SET shift_id = :shift_id,
                            employee_id = :employee_id,
                            equipment_id = :equipment_id,
                            product_id = :product_id,
                            production_order_id = :production_order_id,
                            production_run_id = :production_run_id,
                            linked_staging_id = :linked_staging_id,
                            resolution_status = :resolution_status,
                            resolution_details = CAST(:resolution_details AS jsonb),
                            resolved_at = CASE WHEN :resolution_status = 'RESOLVED' THEN now() ELSE NULL END,
                            processing_status = 'PENDING',
                            error_message = NULL,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {
                        **resolved,
                        "linked_staging_id": linked_id,
                        "resolution_status": status,
                        "resolution_details": json.dumps(details, ensure_ascii=False),
                        "id": event["id"],
                    },
                )

                _write_issues(connection, event["id"], missing, event)
                savepoint.commit()

            except Exception as exc:
                if savepoint.is_active:
                    savepoint.rollback()
                counters["errors"] += 1
                connection.execute(
                    text(
                        """
                        UPDATE external_event_staging
                        SET resolution_status = 'ERROR',
                            processing_status = 'ERROR',
                            error_message = :message,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {"id": event["id"], "message": str(exc)[:2000]},
                )

    return counters


def unresolved_events(limit: int = 200) -> list[dict]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    e.id,
                    e.event_type,
                    e.business_date,
                    e.shift_code,
                    e.personnel_number,
                    e.equipment_code,
                    e.order_no,
                    e.article_code,
                    e.ticket_no,
                    e.resolution_status,
                    e.resolution_details,
                    e.error_message,
                    e.source_document_id,
                    e.source_row
                FROM external_event_staging e
                WHERE e.resolution_status <> 'RESOLVED'
                ORDER BY e.business_date DESC NULLS LAST, e.source_row DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


def add_alias(source_system: str, entity_type: str, external_code: str, entity_id, canonical_label: str | None = None):
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system, entity_type, external_code, entity_id, canonical_label
                ) VALUES (
                    :source_system, :entity_type, :external_code, :entity_id, :canonical_label
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
                "source_system": source_system,
                "entity_type": entity_type,
                "external_code": external_code,
                "entity_id": entity_id,
                "canonical_label": canonical_label,
            },
        )
