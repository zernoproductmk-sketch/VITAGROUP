from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings
from .database import engine


def _as_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _round(value: float | None, digits: int = 1):
    if value is None:
        return None
    return round(value, digits)


def current_business_shift(now: datetime | None = None) -> tuple[date, str]:
    tz = ZoneInfo(settings.business_timezone)
    now = now.astimezone(tz) if now else datetime.now(tz)
    current_time = now.timetz().replace(tzinfo=None)

    if time(9, 0) <= current_time < time(21, 0):
        return now.date(), "DAY"
    if current_time >= time(21, 0):
        return now.date(), "NIGHT"
    return now.date() - timedelta(days=1), "NIGHT"


def _target_shift(
    business_date: date | None,
    shift_code: str | None,
) -> tuple[date, str]:
    if business_date is None and shift_code is None:
        return current_business_shift()

    if business_date is None:
        current_date, _ = current_business_shift()
        business_date = current_date

    if shift_code is None:
        current_date, current_code = current_business_shift()
        shift_code = current_code if business_date == current_date else "DAY"

    shift_code = shift_code.upper()
    if shift_code not in {"DAY", "NIGHT"}:
        raise ValueError("shift_code must be DAY or NIGHT")

    return business_date, shift_code


def _shift_context(
    connection,
    business_date: date,
    shift_code: str,
) -> dict:
    tz = ZoneInfo(settings.business_timezone)
    row = connection.execute(
        text(
            """
            SELECT
                s.id,
                s.business_date,
                s.started_at,
                s.ended_at,
                s.status,
                st.code,
                st.name,
                st.start_time,
                st.end_time,
                st.crosses_midnight
            FROM shift_types st
            LEFT JOIN shifts s
              ON s.shift_type_id = st.id
             AND s.business_date = :business_date
            WHERE st.code = :shift_code
            LIMIT 1
            """
        ),
        {
            "business_date": business_date,
            "shift_code": shift_code,
        },
    ).mappings().first()

    if not row:
        raise RuntimeError(f"Shift type {shift_code} is not configured")

    started_at = row["started_at"]
    ended_at = row["ended_at"]

    if started_at is None:
        started_at = datetime.combine(
            business_date,
            row["start_time"],
            tzinfo=tz,
        )
        end_date = business_date + timedelta(days=1) if row["crosses_midnight"] else business_date
        ended_at = datetime.combine(
            end_date,
            row["end_time"],
            tzinfo=tz,
        )

    now = datetime.now(tz)
    if now <= started_at:
        effective_end = started_at
        display_status = "PLANNED"
    elif now < ended_at:
        effective_end = now
        display_status = "ONLINE"
    else:
        effective_end = ended_at
        display_status = row["status"] or "CLOSED"
        if display_status == "OPEN":
            display_status = "CLOSED"

    return {
        "id": row["id"],
        "business_date": business_date,
        "code": shift_code,
        "name": row["name"],
        "started_at": started_at,
        "ended_at": ended_at,
        "effective_end": effective_end,
        "status": display_status,
        "db_status": row["status"],
    }


RUN_METRICS_SQL = text(
    """
    WITH base AS (
        SELECT
            pr.id,
            pr.shift_id,
            pr.equipment_id,
            pr.product_id,
            pr.production_order_id,
            pr.status AS run_status,
            pr.planned_qty,
            pr.ideal_rate_per_hour,
            pr.planned_start_at,
            pr.planned_end_at,
            pr.actual_start_at,
            pr.actual_end_at,
            e.code AS equipment_code,
            e.name AS equipment_name,
            p.code AS product_code,
            p.article AS product_article,
            p.name AS product_name,
            po.order_no,
            GREATEST(
                COALESCE(pr.actual_start_at, pr.planned_start_at, s.started_at),
                s.started_at
            ) AS calc_start,
            LEAST(
                COALESCE(pr.actual_end_at, pr.planned_end_at, :effective_end),
                :effective_end
            ) AS calc_end
        FROM production_runs pr
        JOIN shifts s ON s.id = pr.shift_id
        JOIN equipment e ON e.id = pr.equipment_id
        JOIN products p ON p.id = pr.product_id
        LEFT JOIN production_orders po ON po.id = pr.production_order_id
        WHERE pr.shift_id = :shift_id
          AND pr.status <> 'CANCELLED'
    )
    SELECT
        b.*,
        GREATEST(EXTRACT(EPOCH FROM (b.calc_end - b.calc_start)), 0) AS planned_seconds,
        COALESCE(outp.output_qty, 0) AS output_qty,
        COALESCE(defs.operator_defect_qty, 0) AS operator_defect_qty,
        COALESCE(defs.qc_defect_qty, 0) AS qc_defect_qty,
        COALESCE(wh.warehouse_qty, 0) AS warehouse_qty,
        COALESCE(erp.erp_qty, 0) AS erp_qty,
        COALESCE(dt.downtime_seconds, 0) AS downtime_seconds,
        active_dt.active_reason
    FROM base b
    LEFT JOIN LATERAL (
        SELECT
            CASE
                WHEN count(*) FILTER (WHERE poe.event_kind = 'FINAL') > 0
                THEN (
                    array_agg(
                        poe.quantity
                        ORDER BY poe.occurred_at DESC, poe.created_at DESC
                    ) FILTER (WHERE poe.event_kind = 'FINAL')
                )[1]
                ELSE COALESCE(
                    sum(poe.quantity)
                    FILTER (WHERE poe.event_kind IN ('INCREMENT','CORRECTION')),
                    0
                )
            END AS output_qty
        FROM production_output_events poe
        WHERE poe.production_run_id = b.id
          AND poe.status <> 'REJECTED'
    ) outp ON true
    LEFT JOIN LATERAL (
        SELECT
            COALESCE(
                sum(de.quantity) FILTER (WHERE de.reported_by = 'OPERATOR'),
                0
            ) AS operator_defect_qty,
            COALESCE(
                sum(de.quantity)
                FILTER (
                    WHERE de.reported_by = 'QC'
                      AND de.is_confirmed = true
                ),
                0
            ) AS qc_defect_qty
        FROM defect_events de
        WHERE de.production_run_id = b.id
    ) defs ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(sum(wr.quantity), 0) AS warehouse_qty
        FROM warehouse_receipts wr
        WHERE wr.production_run_id = b.id
    ) wh ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(sum(epf.quantity), 0) AS erp_qty
        FROM erp_production_facts epf
        WHERE epf.production_run_id = b.id
    ) erp ON true
    LEFT JOIN LATERAL (
        SELECT
            COALESCE(
                sum(
                    GREATEST(
                        EXTRACT(
                            EPOCH FROM (
                                LEAST(COALESCE(dte.ended_at, :effective_end), b.calc_end)
                                -
                                GREATEST(dte.started_at, b.calc_start)
                            )
                        ),
                        0
                    )
                ),
                0
            ) AS downtime_seconds
        FROM downtime_events dte
        LEFT JOIN downtime_reasons dr ON dr.id = dte.reason_id
        WHERE dte.shift_id = b.shift_id
          AND dte.equipment_id = b.equipment_id
          AND (
                dte.production_run_id = b.id
                OR dte.production_run_id IS NULL
              )
          AND dte.is_planned = false
          AND COALESCE(dr.affects_availability, true) = true
          AND dte.started_at < b.calc_end
          AND COALESCE(dte.ended_at, :effective_end) > b.calc_start
    ) dt ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(dr.name, dte.comment, 'Простой') AS active_reason
        FROM downtime_events dte
        LEFT JOIN downtime_reasons dr ON dr.id = dte.reason_id
        WHERE dte.shift_id = b.shift_id
          AND dte.equipment_id = b.equipment_id
          AND dte.started_at <= :now
          AND (dte.ended_at IS NULL OR dte.ended_at > :now)
        ORDER BY dte.started_at DESC
        LIMIT 1
    ) active_dt ON true
    ORDER BY b.equipment_code, b.calc_start, b.order_no
    """
)


def _run_metrics(connection, shift: dict) -> list[dict]:
    if shift["id"] is None:
        return []

    now = datetime.now(ZoneInfo(settings.business_timezone))
    rows = connection.execute(
        RUN_METRICS_SQL,
        {
            "shift_id": shift["id"],
            "effective_end": shift["effective_end"],
            "now": now,
        },
    ).mappings().all()

    result = []
    for raw in rows:
        row = dict(raw)
        planned_seconds = max(_as_float(row["planned_seconds"]), 0)
        downtime_seconds = min(
            max(_as_float(row["downtime_seconds"]), 0),
            planned_seconds,
        )
        runtime_seconds = max(planned_seconds - downtime_seconds, 0)
        output_qty = _as_float(row["output_qty"])
        operator_defect = _as_float(row["operator_defect_qty"])
        qc_defect = _as_float(row["qc_defect_qty"])
        qc_additional_defect = max(qc_defect - operator_defect, 0)
        good_qty = max(output_qty - qc_additional_defect, 0)
        rate = (
            _as_float(row["ideal_rate_per_hour"])
            if row["ideal_rate_per_hour"] is not None
            else None
        )
        theoretical = (
            rate * runtime_seconds / 3600
            if rate is not None and runtime_seconds > 0
            else None
        )

        availability = _pct(runtime_seconds, planned_seconds)
        performance = (
            _pct(output_qty, theoretical)
            if theoretical is not None
            else None
        )
        quality = _pct(good_qty, output_qty)
        oee = None
        if (
            availability is not None
            and performance is not None
            and quality is not None
        ):
            oee = round(
                availability * performance * quality / 10000,
                1,
            )

        result.append(
            {
                "id": str(row["id"]),
                "shift_id": str(row["shift_id"]),
                "equipment_id": str(row["equipment_id"]),
                "equipment_code": row["equipment_code"],
                "equipment_name": row["equipment_name"],
                "product_code": row["product_code"],
                "product_article": row["product_article"],
                "product_name": row["product_name"],
                "order_no": row["order_no"],
                "run_status": row["run_status"],
                "calc_start": row["calc_start"],
                "calc_end": row["calc_end"],
                "planned_qty": _as_float(row["planned_qty"]),
                "ideal_rate_per_hour": rate,
                "planned_minutes": _round(planned_seconds / 60, 1),
                "downtime_minutes": _round(downtime_seconds / 60, 1),
                "runtime_minutes": _round(runtime_seconds / 60, 1),
                "output_qty": output_qty,
                "operator_defect_qty": operator_defect,
                "qc_defect_qty": qc_defect,
                "qc_additional_defect_qty": qc_additional_defect,
                "good_qty": good_qty,
                "warehouse_qty": _as_float(row["warehouse_qty"]),
                "erp_qty": _as_float(row["erp_qty"]),
                "theoretical_qty": _round(theoretical, 3),
                "availability": availability,
                "performance": performance,
                "quality": quality,
                "oee": oee,
                "active_downtime_reason": row["active_reason"],
            }
        )

    return result


def _aggregate_metrics(rows: list[dict]) -> dict:
    planned_seconds = sum((row["planned_minutes"] or 0) * 60 for row in rows)
    downtime_seconds = sum((row["downtime_minutes"] or 0) * 60 for row in rows)
    runtime_seconds = max(planned_seconds - downtime_seconds, 0)

    output_qty = sum(row["output_qty"] for row in rows)
    operator_defect = sum(row["operator_defect_qty"] for row in rows)
    qc_defect = sum(row["qc_defect_qty"] for row in rows)
    qc_additional_defect = sum(row.get("qc_additional_defect_qty", 0) for row in rows)
    good_qty = sum(row["good_qty"] for row in rows)
    warehouse_qty = sum(row["warehouse_qty"] for row in rows)
    erp_qty = sum(row["erp_qty"] for row in rows)
    plan_qty = sum(row["planned_qty"] for row in rows)

    missing_norm_rows = [
        row
        for row in rows
        if (row["planned_minutes"] or 0) > 0
        and row["ideal_rate_per_hour"] is None
    ]
    theoretical_qty = sum(
        row["theoretical_qty"] or 0
        for row in rows
        if row["ideal_rate_per_hour"] is not None
    )

    availability = _pct(runtime_seconds, planned_seconds)
    performance = None
    if not missing_norm_rows:
        performance = _pct(output_qty, theoretical_qty)
    quality = _pct(good_qty, output_qty)

    oee = None
    if (
        availability is not None
        and performance is not None
        and quality is not None
    ):
        oee = round(
            availability * performance * quality / 10000,
            1,
        )

    return {
        "kpi": {
            "oee": oee,
            "availability": availability,
            "performance": performance,
            "quality": quality,
        },
        "production": {
            "plan": _round(plan_qty, 3),
            "operator_output": _round(output_qty, 3),
            "good_product": _round(good_qty, 3),
            "operator_defect": _round(operator_defect, 3),
            "qc_defect": _round(qc_defect, 3),
            "qc_additional_defect": _round(qc_additional_defect, 3),
            "warehouse_received": _round(warehouse_qty, 3),
            "erp_fact": _round(erp_qty, 3),
        },
        "time": {
            "planned_minutes": _round(planned_seconds / 60, 1),
            "downtime_minutes": _round(downtime_seconds / 60, 1),
            "runtime_minutes": _round(runtime_seconds / 60, 1),
        },
        "data_quality": {
            "runs_total": len(rows),
            "missing_norm_runs": len(missing_norm_rows),
            "runs_without_output": sum(
                1 for row in rows if row["output_qty"] <= 0
            ),
        },
    }


def _equipment_metrics(rows: list[dict], shift: dict) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["equipment_code"]].append(row)

    now = datetime.now(ZoneInfo(settings.business_timezone))
    result = []

    for equipment_code, items in groups.items():
        aggregate = _aggregate_metrics(items)
        product_names = []
        for item in items:
            label = item["product_name"]
            if label and label not in product_names:
                product_names.append(label)

        if len(product_names) == 1:
            product_label = product_names[0]
        elif len(product_names) > 1:
            product_label = f"{product_names[0]} + еще {len(product_names) - 1}"
        else:
            product_label = "—"

        active_reason = next(
            (
                item["active_downtime_reason"]
                for item in items
                if item["active_downtime_reason"]
            ),
            None,
        )

        if active_reason:
            state = "DOWNTIME"
        elif now < shift["started_at"]:
            state = "PLANNED"
        elif now >= shift["ended_at"]:
            state = "COMPLETED"
        else:
            state = "RUNNING"

        result.append(
            {
                "code": equipment_code,
                "name": items[0]["equipment_name"],
                "state": state,
                "oee": aggregate["kpi"]["oee"],
                "availability": aggregate["kpi"]["availability"],
                "performance": aggregate["kpi"]["performance"],
                "quality": aggregate["kpi"]["quality"],
                "product": product_label,
                "output": aggregate["production"]["operator_output"],
                "plan": aggregate["production"]["plan"],
                "downtime_minutes": aggregate["time"]["downtime_minutes"],
                "downtime_reason": active_reason,
                "missing_norm_runs": aggregate["data_quality"]["missing_norm_runs"],
                "runs": len(items),
            }
        )

    return sorted(result, key=lambda item: item["code"])


def oee_dashboard_summary(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> dict:
    business_date, shift_code = _target_shift(
        business_date,
        shift_code,
    )

    with engine.begin() as connection:
        shift = _shift_context(
            connection,
            business_date,
            shift_code,
        )
        rows = _run_metrics(connection, shift)

    aggregate = _aggregate_metrics(rows)
    equipment = _equipment_metrics(rows, shift)

    return {
        "mode": "LIVE",
        "status": shift["status"],
        "shift": {
            "id": str(shift["id"]) if shift["id"] else None,
            "business_date": shift["business_date"].isoformat(),
            "type": shift["code"],
            "label": "ДЕНЬ" if shift["code"] == "DAY" else "НОЧЬ",
            "time": "09:00–21:00" if shift["code"] == "DAY" else "21:00–09:00",
            "started_at": shift["started_at"],
            "ended_at": shift["ended_at"],
        },
        **aggregate,
        "equipment": equipment,
    }


def oee_run_rows(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> list[dict]:
    business_date, shift_code = _target_shift(
        business_date,
        shift_code,
    )
    with engine.begin() as connection:
        shift = _shift_context(
            connection,
            business_date,
            shift_code,
        )
        return _run_metrics(connection, shift)


def downtime_rows(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> list[dict]:
    business_date, shift_code = _target_shift(
        business_date,
        shift_code,
    )
    tz = ZoneInfo(settings.business_timezone)

    with engine.begin() as connection:
        shift = _shift_context(
            connection,
            business_date,
            shift_code,
        )
        if shift["id"] is None:
            return []

        rows = connection.execute(
            text(
                """
                SELECT
                    e.code AS equipment,
                    d.started_at,
                    d.ended_at,
                    d.is_planned,
                    COALESCE(dr.name, d.comment, 'Простой') AS reason
                FROM downtime_events d
                JOIN equipment e ON e.id = d.equipment_id
                LEFT JOIN downtime_reasons dr ON dr.id = d.reason_id
                WHERE d.shift_id = :shift_id
                ORDER BY d.started_at DESC
                """
            ),
            {"shift_id": shift["id"]},
        ).mappings().all()

    now = datetime.now(tz)
    result = []
    for row in rows:
        start = row["started_at"]
        end = row["ended_at"]
        duration_end = end or min(now, shift["ended_at"])
        minutes = max(
            (duration_end - start).total_seconds() / 60,
            0,
        )
        result.append(
            {
                "equipment": row["equipment"],
                "start": start.astimezone(tz).strftime("%H:%M"),
                "end": (
                    end.astimezone(tz).strftime("%H:%M")
                    if end
                    else None
                ),
                "minutes": round(minutes, 1),
                "reason": row["reason"],
                "planned": row["is_planned"],
            }
        )
    return result


def reconciliation_rows(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> list[dict]:
    rows = oee_run_rows(business_date, shift_code)
    result = []

    for row in rows:
        product = row["product_article"] or row["product_code"]
        if row["order_no"]:
            product = f"{product} · {row['order_no']}"

        result.append(
            {
                "production_run_id": row["id"],
                "product": product,
                "product_name": row["product_name"],
                "operator": _round(row["output_qty"], 3),
                "operator_defect": _round(
                    row["operator_defect_qty"],
                    3,
                ),
                "qc_defect": _round(row["qc_defect_qty"], 3),
                "qc_good": _round(row["good_qty"], 3),
                "warehouse": _round(row["warehouse_qty"], 3),
                "erp": _round(row["erp_qty"], 3),
                "delta_operator_qc": _round(
                    row["output_qty"] - row["good_qty"],
                    3,
                ),
                "delta_qc_warehouse": _round(
                    row["good_qty"] - row["warehouse_qty"],
                    3,
                ),
                "delta_warehouse_erp": _round(
                    row["warehouse_qty"] - row["erp_qty"],
                    3,
                ),
            }
        )

    return result
