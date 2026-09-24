from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings
from .database import engine
from .oee_service import oee_dashboard_summary, oee_run_rows
from .reconciliation_service import shift_reconciliation


def _as_float(value) -> float:
    return float(value or 0)


def _expected_progress(summary: dict) -> float:
    shift = summary["shift"]
    started = shift["started_at"]
    ended = shift["ended_at"]
    if isinstance(started, str):
        started = datetime.fromisoformat(started)
    if isinstance(ended, str):
        ended = datetime.fromisoformat(ended)

    now = datetime.now(ZoneInfo(settings.business_timezone))
    if now <= started:
        return 0.0
    if now >= ended:
        return 1.0

    duration = (ended - started).total_seconds()
    if duration <= 0:
        return 0.0
    return max(0.0, min(1.0, (now - started).total_seconds() / duration))


def shift_master_dashboard(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> dict:
    summary = oee_dashboard_summary(business_date, shift_code)
    runs = oee_run_rows(
        date.fromisoformat(summary["shift"]["business_date"]),
        summary["shift"]["type"],
    )
    reconciliation = shift_reconciliation(
        date.fromisoformat(summary["shift"]["business_date"]),
        summary["shift"]["type"],
    )

    if not runs:
        return {
            "shift": {**summary["shift"], "status": summary["status"]},
            "kpi": summary["kpi"],
            "production": summary["production"],
            "time": summary["time"],
            "summary": {
                "lines": 0,
                "running": 0,
                "downtime": 0,
                "problem_lines": 0,
                "staff": 0,
            },
            "lines": [],
            "alerts": [],
        }

    run_ids = [UUID(row["id"]) for row in runs]
    recon_by_run = {
        row["production_run_id"]: row
        for row in reconciliation["rows"]
    }

    with engine.begin() as connection:
        staff_rows = connection.execute(
            text(
                """
                SELECT DISTINCT
                    esa.production_run_id,
                    esa.equipment_id,
                    emp.id AS employee_id,
                    emp.personnel_number,
                    emp.full_name,
                    emp.position_name
                FROM employee_shift_assignments esa
                JOIN employees emp ON emp.id = esa.employee_id
                WHERE emp.is_active = true
                  AND (
                        esa.production_run_id = ANY(:run_ids)
                        OR (
                            esa.production_run_id IS NULL
                            AND esa.shift_id = :shift_id
                        )
                      )
                ORDER BY emp.full_name
                """
            ),
            {
                "run_ids": run_ids,
                "shift_id": UUID(summary["shift"]["id"])
                if summary["shift"]["id"]
                else None,
            },
        ).mappings().all()

        active_downtime_rows = connection.execute(
            text(
                """
                SELECT
                    d.id,
                    d.production_run_id,
                    d.equipment_id,
                    d.started_at,
                    COALESCE(dr.name, d.comment, 'Простой') AS reason
                FROM downtime_events d
                LEFT JOIN downtime_reasons dr ON dr.id = d.reason_id
                WHERE d.shift_id = :shift_id
                  AND d.ended_at IS NULL
                ORDER BY d.started_at
                """
            ),
            {
                "shift_id": UUID(summary["shift"]["id"])
                if summary["shift"]["id"]
                else None,
            },
        ).mappings().all()

    staff_by_run: dict[str, list[dict]] = {}
    staff_by_equipment: dict[str, list[dict]] = {}
    unique_staff = set()

    for row in staff_rows:
        item = {
            "id": str(row["employee_id"]),
            "personnel_number": row["personnel_number"],
            "full_name": row["full_name"],
            "position_name": row["position_name"],
        }
        unique_staff.add(str(row["employee_id"]))
        if row["production_run_id"]:
            staff_by_run.setdefault(
                str(row["production_run_id"]),
                [],
            ).append(item)
        if row["equipment_id"]:
            staff_by_equipment.setdefault(
                str(row["equipment_id"]),
                [],
            ).append(item)

    active_by_run = {}
    active_by_equipment = {}
    for row in active_downtime_rows:
        item = {
            "id": str(row["id"]),
            "started_at": row["started_at"].isoformat(),
            "reason": row["reason"],
        }
        if row["production_run_id"]:
            active_by_run[str(row["production_run_id"])] = item
        active_by_equipment[str(row["equipment_id"])] = item

    expected_progress = _expected_progress(summary)
    line_rows = []
    alerts = []

    for run in runs:
        plan = _as_float(run["planned_qty"])
        output = _as_float(run["output_qty"])
        completion = output / plan if plan > 0 else None
        expected_qty = plan * expected_progress if plan > 0 else None
        pace_delta = (
            output - expected_qty
            if expected_qty is not None
            else None
        )
        pace_percent = (
            (output / expected_qty) * 100
            if expected_qty and expected_qty > 0
            else None
        )

        active_downtime = (
            active_by_run.get(run["id"])
            or active_by_equipment.get(run["equipment_id"])
        )
        staff = staff_by_run.get(run["id"]) or staff_by_equipment.get(
            run["equipment_id"],
            [],
        )
        recon = recon_by_run.get(run["id"])

        state = "RUNNING"
        if active_downtime:
            state = "DOWNTIME"
        elif run["run_status"] in {"COMPLETED", "VERIFIED"}:
            state = run["run_status"]
        elif run["run_status"] == "PLANNED":
            state = "PLANNED"

        line_alerts = []
        if active_downtime:
            line_alerts.append(
                {
                    "type": "DOWNTIME",
                    "severity": "CRITICAL",
                    "message": active_downtime["reason"],
                }
            )
        if run["ideal_rate_per_hour"] is None:
            line_alerts.append(
                {
                    "type": "MISSING_NORM",
                    "severity": "WARNING",
                    "message": "Не найден норматив скорости",
                }
            )
        if (
            expected_progress >= 0.1
            and pace_percent is not None
            and pace_percent < 90
            and state not in {"PLANNED", "COMPLETED", "VERIFIED"}
        ):
            line_alerts.append(
                {
                    "type": "PACE",
                    "severity": "WARNING",
                    "message": f"Темп {pace_percent:.1f}% от ожидаемого",
                }
            )
        if recon and recon["severity"] != "OK":
            line_alerts.append(
                {
                    "type": "RECONCILIATION",
                    "severity": recon["severity"],
                    "message": "Есть расхождение по учету",
                }
            )

        line = {
            "production_run_id": run["id"],
            "equipment_id": run["equipment_id"],
            "equipment_code": run["equipment_code"],
            "equipment_name": run["equipment_name"],
            "order_no": run["order_no"],
            "product_article": (
                run["product_article"] or run["product_code"]
            ),
            "product_name": run["product_name"],
            "state": state,
            "planned_qty": plan,
            "output_qty": output,
            "good_qty": _as_float(run["good_qty"]),
            "operator_defect_qty": _as_float(
                run["operator_defect_qty"]
            ),
            "qc_defect_qty": _as_float(run["qc_defect_qty"]),
            "completion_percent": (
                round(completion * 100, 1)
                if completion is not None
                else None
            ),
            "expected_qty_now": (
                round(expected_qty, 1)
                if expected_qty is not None
                else None
            ),
            "pace_delta_qty": (
                round(pace_delta, 1)
                if pace_delta is not None
                else None
            ),
            "pace_percent": (
                round(pace_percent, 1)
                if pace_percent is not None
                else None
            ),
            "oee": run["oee"],
            "availability": run["availability"],
            "performance": run["performance"],
            "quality": run["quality"],
            "downtime_minutes": run["downtime_minutes"],
            "active_downtime": active_downtime,
            "staff": staff,
            "reconciliation": {
                "severity": recon["severity"],
                "primary_issue": recon["primary_issue"],
                "case_status": (
                    recon["case"]["status"]
                    if recon.get("case")
                    else None
                ),
            } if recon else None,
            "alerts": line_alerts,
        }
        line_rows.append(line)

        for alert in line_alerts:
            alerts.append(
                {
                    **alert,
                    "production_run_id": run["id"],
                    "equipment_code": run["equipment_code"],
                    "order_no": run["order_no"],
                }
            )

    alerts.sort(
        key=lambda item: (
            0 if item["severity"] == "CRITICAL" else 1,
            item["equipment_code"],
        )
    )

    return {
        "shift": {**summary["shift"], "status": summary["status"]},
        "kpi": summary["kpi"],
        "production": summary["production"],
        "time": summary["time"],
        "expected_progress_percent": round(
            expected_progress * 100,
            1,
        ),
        "summary": {
            "lines": len(line_rows),
            "running": sum(
                1 for row in line_rows if row["state"] == "RUNNING"
            ),
            "downtime": sum(
                1 for row in line_rows if row["state"] == "DOWNTIME"
            ),
            "problem_lines": sum(
                1 for row in line_rows if row["alerts"]
            ),
            "staff": len(unique_staff),
        },
        "lines": line_rows,
        "alerts": alerts,
    }


def shift_close_readiness(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> dict:
    dashboard = shift_master_dashboard(business_date, shift_code)
    shift_id = dashboard["shift"].get("id")

    blockers = []
    warnings = []

    if not shift_id:
        blockers.append({
            "code": "SHIFT_NOT_CREATED",
            "message": "Смена еще не создана в базе",
        })
        return {
            "ready": False,
            "shift": dashboard["shift"],
            "blockers": blockers,
            "warnings": warnings,
        }

    if dashboard["summary"]["downtime"] > 0:
        blockers.append({
            "code": "ACTIVE_DOWNTIME",
            "message": f"Есть активные простои: {dashboard['summary']['downtime']}",
        })

    unfinished = [
        line for line in dashboard["lines"]
        if line["state"] not in {"COMPLETED", "VERIFIED"}
    ]
    if unfinished:
        blockers.append({
            "code": "UNFINISHED_RUNS",
            "message": f"Не завершены производственные запуски: {len(unfinished)}",
        })

    open_reconciliation = [
        line for line in dashboard["lines"]
        if line.get("reconciliation")
        and line["reconciliation"]["severity"] != "OK"
        and line["reconciliation"].get("case_status") != "RESOLVED"
    ]
    if open_reconciliation:
        blockers.append({
            "code": "OPEN_RECONCILIATION",
            "message": f"Есть незакрытые расхождения: {len(open_reconciliation)}",
        })

    missing_norm = [
        line for line in dashboard["lines"]
        if any(a["type"] == "MISSING_NORM" for a in line.get("alerts", []))
    ]
    if missing_norm:
        warnings.append({
            "code": "MISSING_NORM",
            "message": f"Нет норматива скорости у запусков: {len(missing_norm)}",
        })

    no_staff = [
        line for line in dashboard["lines"]
        if not line.get("staff")
    ]
    if no_staff:
        warnings.append({
            "code": "NO_STAFF_ASSIGNMENT",
            "message": f"Не определены сотрудники на линиях: {len(no_staff)}",
        })

    return {
        "ready": len(blockers) == 0,
        "shift": dashboard["shift"],
        "blockers": blockers,
        "warnings": warnings,
    }


def close_shift(
    business_date: date,
    shift_code: str,
    user_id: UUID,
) -> dict:
    readiness = shift_close_readiness(business_date, shift_code)
    if not readiness["ready"]:
        raise ValueError("Смена не готова к закрытию")

    shift_id = readiness["shift"].get("id")
    if not shift_id:
        raise ValueError("Смена не найдена")

    with engine.begin() as connection:
        old = connection.execute(
            text(
                """
                SELECT id, status
                FROM shifts
                WHERE id = :shift_id
                FOR UPDATE
                """
            ),
            {"shift_id": UUID(shift_id)},
        ).mappings().first()

        if not old:
            raise LookupError("Смена не найдена")

        if old["status"] == "CLOSED":
            return {
                "status": "CLOSED",
                "shift_id": shift_id,
                "already_closed": True,
            }

        if old["status"] == "VERIFIED":
            return {
                "status": "VERIFIED",
                "shift_id": shift_id,
                "already_closed": True,
            }

        connection.execute(
            text(
                """
                UPDATE shifts
                SET status = 'CLOSED'
                WHERE id = :shift_id
                """
            ),
            {"shift_id": UUID(shift_id)},
        )

        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    table_name,
                    record_id,
                    action,
                    changed_by_user_id,
                    old_data,
                    new_data,
                    reason
                ) VALUES (
                    'shifts',
                    :shift_id,
                    'UPDATE',
                    :user_id,
                    jsonb_build_object('status', :old_status),
                    jsonb_build_object('status', 'CLOSED'),
                    'Закрытие смены сменным мастером / руководителем производства'
                )
                """
            ),
            {
                "shift_id": UUID(shift_id),
                "user_id": user_id,
                "old_status": old["status"],
            },
        )

    return {
        "status": "CLOSED",
        "shift_id": shift_id,
        "already_closed": False,
    }


def complete_production_run(
    production_run_id: UUID,
    user_id: UUID,
) -> dict:
    now = datetime.now(ZoneInfo(settings.business_timezone))

    with engine.begin() as connection:
        run = connection.execute(
            text(
                """
                SELECT
                    pr.id,
                    pr.status,
                    pr.actual_start_at,
                    pr.actual_end_at,
                    pr.shift_id,
                    pr.equipment_id
                FROM production_runs pr
                WHERE pr.id = :run_id
                FOR UPDATE
                """
            ),
            {"run_id": production_run_id},
        ).mappings().first()

        if not run:
            raise LookupError("Производственный запуск не найден")

        if run["status"] in {"COMPLETED", "VERIFIED"}:
            return {
                "status": run["status"],
                "production_run_id": str(production_run_id),
                "already_completed": True,
            }

        if run["status"] == "CANCELLED":
            raise ValueError("Отмененный запуск нельзя завершить")

        active_downtime = connection.execute(
            text(
                """
                SELECT 1
                FROM downtime_events
                WHERE shift_id = :shift_id
                  AND equipment_id = :equipment_id
                  AND ended_at IS NULL
                  AND (
                        production_run_id = :run_id
                        OR production_run_id IS NULL
                      )
                LIMIT 1
                """
            ),
            {
                "shift_id": run["shift_id"],
                "equipment_id": run["equipment_id"],
                "run_id": production_run_id,
            },
        ).scalar_one_or_none()

        if active_downtime:
            raise ValueError(
                "Сначала завершите активный простой на линии"
            )

        actual_start_at = run["actual_start_at"] or now
        actual_end_at = max(now, actual_start_at)

        connection.execute(
            text(
                """
                UPDATE production_runs
                SET status = 'COMPLETED',
                    actual_start_at = COALESCE(actual_start_at, :actual_start_at),
                    actual_end_at = :actual_end_at,
                    updated_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": production_run_id,
                "actual_start_at": actual_start_at,
                "actual_end_at": actual_end_at,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    table_name,
                    record_id,
                    action,
                    changed_by_user_id,
                    old_data,
                    new_data,
                    reason
                ) VALUES (
                    'production_runs',
                    :run_id,
                    'UPDATE',
                    :user_id,
                    jsonb_build_object('status', :old_status),
                    jsonb_build_object(
                        'status', 'COMPLETED',
                        'actual_end_at', :actual_end_at
                    ),
                    'Завершение производственного запуска сменным мастером'
                )
                """
            ),
            {
                "run_id": production_run_id,
                "user_id": user_id,
                "old_status": run["status"],
                "actual_end_at": actual_end_at,
            },
        )

    return {
        "status": "COMPLETED",
        "production_run_id": str(production_run_id),
        "already_completed": False,
        "actual_end_at": actual_end_at.isoformat(),
    }
