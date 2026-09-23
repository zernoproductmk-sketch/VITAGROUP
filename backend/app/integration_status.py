from sqlalchemy import text

from .database import engine


def integration_dashboard() -> dict:
    with engine.begin() as connection:
        event_counts = {
            row["event_type"]: {
                "total": row["total"],
                "resolved": row["resolved"],
                "partial": row["partial"],
                "errors": row["errors"],
                "promoted": row["promoted"],
            }
            for row in connection.execute(
                text(
                    """
                    SELECT
                        event_type,
                        count(*) AS total,
                        count(*) FILTER (WHERE resolution_status = 'RESOLVED') AS resolved,
                        count(*) FILTER (WHERE resolution_status = 'PARTIAL') AS partial,
                        count(*) FILTER (WHERE resolution_status = 'ERROR') AS errors,
                        count(*) FILTER (WHERE processing_status = 'RESOLVED') AS promoted
                    FROM external_event_staging
                    GROUP BY event_type
                    """
                )
            ).mappings()
        }

        master_logs = {
            row["source_key"]: dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (source_key)
                        source_key,
                        status,
                        started_at,
                        completed_at,
                        rows_read,
                        rows_applied,
                        rows_skipped,
                        rows_error,
                        message
                    FROM master_data_sync_log
                    ORDER BY source_key, started_at DESC
                    """
                )
            ).mappings()
        }

        unresolved_count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM external_event_staging
                WHERE resolution_status <> 'RESOLVED'
                """
            )
        ).scalar_one()

        open_issues = connection.execute(
            text(
                """
                SELECT count(*)
                FROM resolution_issues
                WHERE status = 'OPEN'
                """
            )
        ).scalar_one()

        master_issues = connection.execute(
            text(
                """
                SELECT count(*)
                FROM master_data_sync_issues
                WHERE status = 'OPEN'
                """
            )
        ).scalar_one()

    return {
        "event_sources": event_counts,
        "master_sources": master_logs,
        "totals": {
            "unresolved": unresolved_count,
            "open_resolution_issues": open_issues,
            "open_master_issues": master_issues,
        },
    }


def reference_candidates(entity_type: str, query: str = "", limit: int = 30) -> list[dict]:
    query_like = f"%{query.strip()}%"
    with engine.begin() as connection:
        if entity_type == "EMPLOYEE":
            rows = connection.execute(
                text(
                    """
                    SELECT id, personnel_number AS code, full_name AS label,
                           position_name AS secondary
                    FROM employees
                    WHERE is_active = true
                      AND (:q = '%%' OR personnel_number ILIKE :q OR full_name ILIKE :q)
                    ORDER BY full_name
                    LIMIT :limit
                    """
                ),
                {"q": query_like, "limit": limit},
            ).mappings()
        elif entity_type == "EQUIPMENT":
            rows = connection.execute(
                text(
                    """
                    SELECT id, code, name AS label, NULL::text AS secondary
                    FROM equipment
                    WHERE is_active = true
                      AND (:q = '%%' OR code ILIKE :q OR name ILIKE :q)
                    ORDER BY code
                    LIMIT :limit
                    """
                ),
                {"q": query_like, "limit": limit},
            ).mappings()
        elif entity_type == "PRODUCT":
            rows = connection.execute(
                text(
                    """
                    SELECT id, code, name AS label, article AS secondary
                    FROM products
                    WHERE is_active = true
                      AND (:q = '%%' OR code ILIKE :q OR article ILIKE :q OR name ILIKE :q)
                    ORDER BY code
                    LIMIT :limit
                    """
                ),
                {"q": query_like, "limit": limit},
            ).mappings()
        elif entity_type == "PRODUCTION_ORDER":
            rows = connection.execute(
                text(
                    """
                    SELECT po.id, po.order_no AS code, p.name AS label, p.article AS secondary
                    FROM production_orders po
                    JOIN products p ON p.id = po.product_id
                    WHERE :q = '%%' OR po.order_no ILIKE :q OR p.name ILIKE :q
                    ORDER BY po.order_no DESC
                    LIMIT :limit
                    """
                ),
                {"q": query_like, "limit": limit},
            ).mappings()
        else:
            return []

        return [dict(row) for row in rows]
