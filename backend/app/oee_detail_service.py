from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings
from .database import engine
from .oee_service import _run_metrics, _shift_context


def _serialize_event_row(row: dict) -> dict:
    result = dict(row)
    for key, value in list(result.items()):
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, UUID):
            result[key] = str(value)
    return result


def oee_run_detail(run_id: UUID) -> dict | None:
    tz = ZoneInfo(settings.business_timezone)

    with engine.begin() as connection:
        context = connection.execute(
            text(
                """
                SELECT
                    pr.id,
                    s.business_date,
                    st.code AS shift_code
                FROM production_runs pr
                JOIN shifts s ON s.id = pr.shift_id
                JOIN shift_types st ON st.id = s.shift_type_id
                WHERE pr.id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().first()

        if not context:
            return None

        shift = _shift_context(
            connection,
            context["business_date"],
            context["shift_code"],
        )
        metrics = next(
            (
                row
                for row in _run_metrics(connection, shift)
                if row["id"] == str(run_id)
            ),
            None,
        )
        if not metrics:
            return None

        downtime = connection.execute(
            text(
                """
                SELECT
                    d.id,
                    d.started_at,
                    d.ended_at,
                    d.is_planned,
                    COALESCE(dr.name, d.comment, 'Простой') AS reason,
                    COALESCE(dr.affects_availability, true) AS affects_availability,
                    d.comment
                FROM downtime_events d
                LEFT JOIN downtime_reasons dr ON dr.id = d.reason_id
                WHERE d.shift_id = :shift_id
                  AND d.equipment_id = :equipment_id
                  AND (
                        d.production_run_id = :run_id
                        OR d.production_run_id IS NULL
                      )
                  AND d.started_at < :calc_end
                  AND COALESCE(d.ended_at, :effective_end) > :calc_start
                ORDER BY d.started_at
                """
            ),
            {
                "shift_id": metrics["shift_id"],
                "equipment_id": metrics["equipment_id"],
                "run_id": run_id,
                "calc_start": metrics["calc_start"],
                "calc_end": metrics["calc_end"],
                "effective_end": shift["effective_end"],
            },
        ).mappings().all()

        output_events = connection.execute(
            text(
                """
                SELECT
                    id,
                    occurred_at,
                    quantity,
                    event_kind,
                    status,
                    source_system,
                    source_record_id,
                    comment
                FROM production_output_events
                WHERE production_run_id = :run_id
                ORDER BY occurred_at, created_at
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        defect_events = connection.execute(
            text(
                """
                SELECT
                    id,
                    occurred_at,
                    quantity,
                    reported_by,
                    is_confirmed,
                    source_system,
                    source_record_id,
                    comment
                FROM defect_events
                WHERE production_run_id = :run_id
                ORDER BY occurred_at, created_at
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        warehouse = connection.execute(
            text(
                """
                SELECT
                    id,
                    received_at,
                    quantity,
                    warehouse_document_no,
                    source_system,
                    source_record_id
                FROM warehouse_receipts
                WHERE production_run_id = :run_id
                ORDER BY received_at, created_at
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        erp = connection.execute(
            text(
                """
                SELECT
                    id,
                    erp_document_id,
                    erp_document_no,
                    occurred_at,
                    quantity,
                    defect_quantity,
                    created_at
                FROM erp_production_facts
                WHERE production_run_id = :run_id
                ORDER BY occurred_at, created_at
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

    now = datetime.now(tz)
    downtime_rows = []
    for raw in downtime:
        row = dict(raw)
        end = row["ended_at"] or min(now, shift["effective_end"])
        overlap_start = max(row["started_at"], metrics["calc_start"])
        overlap_end = min(end, metrics["calc_end"])
        overlap_minutes = max(
            (overlap_end - overlap_start).total_seconds() / 60,
            0,
        )
        row["overlap_minutes"] = round(overlap_minutes, 1)
        row["counted_in_availability"] = (
            not row["is_planned"]
            and bool(row["affects_availability"])
        )
        downtime_rows.append(_serialize_event_row(row))

    warnings = []
    if metrics["ideal_rate_per_hour"] is None:
        warnings.append("Для запуска не найден норматив скорости: Performance и OEE не рассчитываются.")
    if metrics["output_qty"] <= 0:
        warnings.append("По запуску пока нет зарегистрированного выпуска.")
    if any(
        item["reason"] == "Простой"
        for item in downtime_rows
    ):
        warnings.append("Есть простой без классифицированной причины.")

    formula = {
        "availability": {
            "formula": "Run Time / Planned Time",
            "numerator": metrics["runtime_minutes"],
            "denominator": metrics["planned_minutes"],
            "result": metrics["availability"],
            "unit": "мин",
        },
        "performance": {
            "formula": "Actual Output / (Ideal Rate × Run Time)",
            "numerator": metrics["output_qty"],
            "denominator": metrics["theoretical_qty"],
            "result": metrics["performance"],
            "unit": "шт",
            "ideal_rate_per_hour": metrics["ideal_rate_per_hour"],
        },
        "quality": {
            "formula": "Good Count / Total Count",
            "numerator": metrics["good_qty"],
            "denominator": metrics["total_count_qty"],
            "result": metrics["quality"],
            "unit": "шт",
            "operator_defect": metrics["operator_defect_qty"],
            "confirmed_qc_defect": metrics["qc_defect_qty"],
        },
        "oee": {
            "formula": "Availability × Performance × Quality",
            "availability": metrics["availability"],
            "performance": metrics["performance"],
            "quality": metrics["quality"],
            "result": metrics["oee"],
        },
    }

    return {
        "run": {
            **metrics,
            "business_date": shift["business_date"].isoformat(),
            "shift_code": shift["code"],
            "shift_status": shift["status"],
            "shift_started_at": shift["started_at"].isoformat(),
            "shift_ended_at": shift["ended_at"].isoformat(),
        },
        "formula": formula,
        "warnings": warnings,
        "events": {
            "output": [_serialize_event_row(dict(row)) for row in output_events],
            "downtime": downtime_rows,
            "defects": [_serialize_event_row(dict(row)) for row in defect_events],
            "warehouse": [_serialize_event_row(dict(row)) for row in warehouse],
            "erp": [_serialize_event_row(dict(row)) for row in erp],
        },
    }
