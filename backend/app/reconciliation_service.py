from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text

from .database import engine
from .oee_service import oee_run_rows


REASON_OPTIONS = [
    {"code": "OPERATOR_ENTRY", "label": "Ошибка / задержка ввода оператора"},
    {"code": "QC_DIFFERENCE", "label": "Расхождение с ОТК"},
    {"code": "ACCOUNTANT_DIFFERENCE", "label": "Расхождение с учетчиком"},
    {"code": "WAREHOUSE_DIFFERENCE", "label": "Расхождение со складом"},
    {"code": "ERP_NOT_POSTED", "label": "ERP еще не проведен / не загружен"},
    {"code": "DOCUMENT_ERROR", "label": "Ошибка документа / талона"},
    {"code": "OTHER", "label": "Другая причина"},
]


def _float(value) -> float:
    return float(value or 0)


def _severity(delta: float, base: float) -> str:
    absolute = abs(delta)
    if absolute < 0.0001:
        return "OK"
    ratio = absolute / abs(base) if abs(base) > 0 else None
    if absolute >= 100 or (ratio is not None and ratio >= 0.02):
        return "CRITICAL"
    return "WARNING"


def _primary_issue(row: dict) -> str | None:
    chain = [
        ("OPERATOR_QC", row["delta_operator_qc"]),
        ("QC_ACCOUNTANT", row["delta_qc_accountant"]),
        ("ACCOUNTANT_WAREHOUSE", row["delta_accountant_warehouse"]),
        ("WAREHOUSE_ERP", row["delta_warehouse_erp"]),
    ]
    for code, delta in chain:
        if abs(delta) > 0.0001:
            return code
    if row["plan_qty"] and abs(row["plan_delta"]) > 0.0001:
        return "PLAN_OPERATOR"
    return None



def _current_stage(row: dict) -> tuple[str, str]:
    if not row["operator_entered"]:
        return "OPERATOR", "Ожидается выпуск оператора"
    if not row["qc_entered"]:
        return "QC", "Ожидается проверка ОТК"
    if not row["accountant_entered"]:
        return "ACCOUNTANT", "Ожидается учет готовой продукции"
    if not row["warehouse_entered"]:
        return "WAREHOUSE", "Ожидается приемка складом"
    if not row["erp_entered"]:
        return "ERP", "Ожидается факт 1С:ERP"
    return "COMPLETE", "Цепочка завершена"


def _stage_severity(row: dict) -> str:
    checks = []
    if row["qc_entered"]:
        checks.append(_severity(row["delta_operator_qc"], row["operator_qty"]))
    if row["accountant_entered"]:
        checks.append(_severity(row["delta_qc_accountant"], row["qc_good_qty"]))
    if row["warehouse_entered"]:
        checks.append(_severity(row["delta_accountant_warehouse"], row["accounting_qty"]))
    if row["erp_entered"]:
        checks.append(_severity(row["delta_warehouse_erp"], row["warehouse_qty"]))

    if "CRITICAL" in checks:
        return "CRITICAL"
    if "WARNING" in checks:
        return "WARNING"
    return "OK" if row["current_stage"] == "COMPLETE" else "PENDING"


def _stage_issue(row: dict) -> str | None:
    checks = [
        ("OPERATOR_QC", "qc_entered", row["delta_operator_qc"]),
        ("QC_ACCOUNTANT", "accountant_entered", row["delta_qc_accountant"]),
        ("ACCOUNTANT_WAREHOUSE", "warehouse_entered", row["delta_accountant_warehouse"]),
        ("WAREHOUSE_ERP", "erp_entered", row["delta_warehouse_erp"]),
    ]
    for code, flag, delta in checks:
        if row[flag] and abs(delta) > 0.0001:
            return code
    return None

def shift_reconciliation(
    business_date: date | None,
    shift_code: str | None,
) -> dict:
    runs = oee_run_rows(business_date, shift_code)
    if not runs:
        return {
            "summary": {
                "runs": 0,
                "ok": 0,
                "warning": 0,
                "critical": 0,
                "pending": 0,
                "open_cases": 0,
            },
            "rows": [],
            "reason_options": REASON_OPTIONS,
        }

    run_ids = [UUID(row["id"]) for row in runs]

    with engine.begin() as connection:
        accounting_rows = connection.execute(
            text(
                """
                SELECT
                    production_run_id,
                    COALESCE(sum(quantity), 0) AS accounting_qty
                FROM accounting_control_events
                WHERE production_run_id = ANY(:run_ids)
                GROUP BY production_run_id
                """
            ),
            {"run_ids": run_ids},
        ).mappings().all()
        accounting = {
            str(row["production_run_id"]): _float(row["accounting_qty"])
            for row in accounting_rows
        }

        stage_rows = connection.execute(
            text(
                """
                SELECT
                    pr.id AS production_run_id,
                    EXISTS (
                        SELECT 1 FROM production_output_events poe
                        WHERE poe.production_run_id = pr.id
                          AND poe.status <> 'REJECTED'
                    ) AS operator_entered,
                    (
                        EXISTS (
                            SELECT 1 FROM qc_inspections qi
                            WHERE qi.production_run_id = pr.id
                        )
                        OR EXISTS (
                            SELECT 1 FROM defect_events de
                            WHERE de.production_run_id = pr.id
                              AND de.reported_by = 'QC'
                              AND de.is_confirmed = true
                        )
                    ) AS qc_entered,
                    EXISTS (
                        SELECT 1 FROM accounting_control_events ace
                        WHERE ace.production_run_id = pr.id
                    ) AS accountant_entered,
                    EXISTS (
                        SELECT 1 FROM warehouse_receipts wr
                        WHERE wr.production_run_id = pr.id
                    ) AS warehouse_entered,
                    EXISTS (
                        SELECT 1 FROM erp_production_facts epf
                        WHERE epf.production_run_id = pr.id
                    ) AS erp_entered
                FROM production_runs pr
                WHERE pr.id = ANY(:run_ids)
                """
            ),
            {"run_ids": run_ids},
        ).mappings().all()
        stages = {
            str(row["production_run_id"]): dict(row)
            for row in stage_rows
        }

        case_rows = connection.execute(
            text(
                """
                SELECT
                    id,
                    production_run_id,
                    status,
                    reason_code,
                    comment,
                    updated_at,
                    resolved_at
                FROM reconciliation_cases
                WHERE production_run_id = ANY(:run_ids)
                """
            ),
            {"run_ids": run_ids},
        ).mappings().all()
        cases = {
            str(row["production_run_id"]): {
                **dict(row),
                "id": str(row["id"]),
                "production_run_id": str(row["production_run_id"]),
            }
            for row in case_rows
        }

    result = []
    counters = {"ok": 0, "warning": 0, "critical": 0, "pending": 0}

    for run in runs:
        operator = _float(run["output_qty"])
        qc_good = _float(run["good_qty"])
        accountant = accounting.get(run["id"], 0.0)
        warehouse = _float(run["warehouse_qty"])
        erp = _float(run["erp_qty"])
        plan = _float(run["planned_qty"])
        flags = stages.get(run["id"], {})

        row = {
            "production_run_id": run["id"],
            "equipment_code": run["equipment_code"],
            "equipment_name": run["equipment_name"],
            "order_no": run["order_no"],
            "product_article": run["product_article"] or run["product_code"],
            "product_name": run["product_name"],
            "plan_qty": plan,
            "operator_qty": operator,
            "operator_defect_qty": _float(run["operator_defect_qty"]),
            "qc_defect_qty": _float(run["qc_defect_qty"]),
            "qc_good_qty": qc_good,
            "accounting_qty": accountant,
            "warehouse_qty": warehouse,
            "erp_qty": erp,
            "plan_delta": operator - plan,
            "delta_operator_qc": operator - qc_good,
            "delta_qc_accountant": qc_good - accountant,
            "delta_accountant_warehouse": accountant - warehouse,
            "delta_warehouse_erp": warehouse - erp,
            "case": cases.get(run["id"]),
            "operator_entered": bool(flags.get("operator_entered")),
            "qc_entered": bool(flags.get("qc_entered")),
            "accountant_entered": bool(flags.get("accountant_entered")),
            "warehouse_entered": bool(flags.get("warehouse_entered")),
            "erp_entered": bool(flags.get("erp_entered")),
        }

        row["current_stage"], row["stage_label"] = _current_stage(row)
        row["severity"] = _stage_severity(row)
        row["primary_issue"] = _stage_issue(row)
        counters[row["severity"].lower()] += 1
        result.append(row)

    return {
        "summary": {
            "runs": len(result),
            **counters,
            "open_cases": sum(
                1
                for row in result
                if row["severity"] != "OK"
                and (
                    row["case"] is None
                    or row["case"]["status"] != "RESOLVED"
                )
            ),
        },
        "rows": result,
        "reason_options": REASON_OPTIONS,
    }


def save_reconciliation_case(
    *,
    production_run_id: UUID,
    status: str,
    reason_code: str | None,
    comment: str | None,
    user_id: UUID,
) -> dict:
    if status not in {"OPEN", "EXPLAINED", "RESOLVED"}:
        raise ValueError("Unsupported reconciliation status")
    if reason_code and reason_code not in {item["code"] for item in REASON_OPTIONS}:
        raise ValueError("Unsupported reconciliation reason")

    with engine.begin() as connection:
        exists = connection.execute(
            text(
                """
                SELECT 1
                FROM production_runs
                WHERE id = :production_run_id
                """
            ),
            {"production_run_id": production_run_id},
        ).scalar_one_or_none()
        if not exists:
            raise LookupError("Production run not found")

        row = connection.execute(
            text(
                """
                INSERT INTO reconciliation_cases (
                    production_run_id,
                    status,
                    reason_code,
                    comment,
                    created_by_user_id,
                    updated_by_user_id,
                    resolved_at
                ) VALUES (
                    :production_run_id,
                    :status,
                    :reason_code,
                    :comment,
                    :user_id,
                    :user_id,
                    CASE WHEN :status = 'RESOLVED' THEN now() ELSE NULL END
                )
                ON CONFLICT (production_run_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    reason_code = EXCLUDED.reason_code,
                    comment = EXCLUDED.comment,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = now(),
                    resolved_at = CASE
                        WHEN EXCLUDED.status = 'RESOLVED'
                        THEN COALESCE(reconciliation_cases.resolved_at, now())
                        ELSE NULL
                    END
                RETURNING *
                """
            ),
            {
                "production_run_id": production_run_id,
                "status": status,
                "reason_code": reason_code,
                "comment": comment,
                "user_id": user_id,
            },
        ).mappings().one()

    return {
        **dict(row),
        "id": str(row["id"]),
        "production_run_id": str(row["production_run_id"]),
    }
