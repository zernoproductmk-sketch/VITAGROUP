from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text

from .database import engine
from .reconciliation_service import shift_reconciliation
from .test_shift_service import test_shift_context


def _stage(
    key: str,
    title: str,
    status: str,
    message: str,
    target_section: str,
) -> dict:
    return {
        "key": key,
        "title": title,
        "status": status,
        "message": message,
        "target_section": target_section,
    }


def shift_lifecycle_status(
    business_date: date,
    shift_code: str,
) -> dict:
    context = test_shift_context(business_date, shift_code)
    shift = context["shift"]
    runs = context["runs"]

    if not shift.get("id"):
        return {
            "shift": shift,
            "summary": {
                "completed_steps": 0,
                "total_steps": 10,
                "verified": False,
            },
            "stages": [
                _stage(
                    "shift",
                    "Смена",
                    "BLOCKED",
                    "Смена еще не создана",
                    "test-shift",
                )
            ],
        }

    run_ids = [UUID(row["id"]) for row in runs]

    with engine.begin() as connection:
        facts = connection.execute(
            text(
                """
                SELECT
                    pr.id AS run_id,
                    pr.status AS run_status,
                    EXISTS (
                        SELECT 1
                        FROM production_output_events poe
                        WHERE poe.production_run_id=pr.id
                          AND poe.status <> 'REJECTED'
                    ) AS has_operator_output,
                    EXISTS (
                        SELECT 1
                        FROM defect_events de
                        WHERE de.production_run_id=pr.id
                          AND de.reported_by='QC'
                          AND de.is_confirmed=true
                    ) AS has_qc,
                    EXISTS (
                        SELECT 1
                        FROM accounting_control_events ace
                        WHERE ace.production_run_id=pr.id
                    ) AS has_accounting,
                    EXISTS (
                        SELECT 1
                        FROM warehouse_receipts wr
                        WHERE wr.production_run_id=pr.id
                    ) AS has_warehouse,
                    EXISTS (
                        SELECT 1
                        FROM erp_production_facts epf
                        WHERE epf.production_run_id=pr.id
                    ) AS has_erp
                FROM production_runs pr
                WHERE pr.id = ANY(:run_ids)
                """
            ),
            {"run_ids": run_ids},
        ).mappings().all() if run_ids else []

    reconciliation = shift_reconciliation(
        business_date,
        shift_code,
    )

    run_count = len(runs)
    with_norm = sum(
        1 for row in runs
        if row["ideal_rate_per_hour"] is not None
    )
    with_staff = sum(
        1 for row in runs
        if row["staff"]
    )

    operator_count = sum(
        1 for row in facts if row["has_operator_output"]
    )
    qc_count = sum(
        1 for row in facts if row["has_qc"]
    )
    accounting_count = sum(
        1 for row in facts if row["has_accounting"]
    )
    warehouse_count = sum(
        1 for row in facts if row["has_warehouse"]
    )
    erp_count = sum(
        1 for row in facts if row["has_erp"]
    )
    finished_count = sum(
        1 for row in facts
        if row["run_status"] in {"COMPLETED", "VERIFIED"}
    )

    def complete(count: int) -> bool:
        return run_count > 0 and count == run_count

    stages = [
        _stage(
            "plan",
            "План и производственные запуски",
            "READY" if run_count > 0 else "BLOCKED",
            (
                f"Создано запусков: {run_count}"
                if run_count
                else "Нет производственных запусков"
            ),
            "erp-plan",
        ),
        _stage(
            "norms",
            "Нормативы скорости",
            "READY" if complete(with_norm) else "BLOCKED",
            f"С нормой: {with_norm} из {run_count}",
            "norms",
        ),
        _stage(
            "staff",
            "Сотрудники на линиях",
            "READY" if complete(with_staff) else "BLOCKED",
            f"С назначениями: {with_staff} из {run_count}",
            "test-shift",
        ),
        _stage(
            "operator",
            "Факт оператора",
            "READY" if complete(operator_count) else "PENDING",
            f"Есть выпуск: {operator_count} из {run_count}",
            "operator-workspace",
        ),
        _stage(
            "qc",
            "Контроль ОТК",
            "READY" if complete(qc_count) else "PENDING",
            f"Есть подтвержденные записи ОТК: {qc_count} из {run_count}",
            "qc-workspace",
        ),
        _stage(
            "accounting",
            "Учет выпуска",
            "READY" if complete(accounting_count) else "PENDING",
            f"Есть данные учетчика: {accounting_count} из {run_count}",
            "accountant-workspace",
        ),
        _stage(
            "warehouse",
            "Приемка складом",
            "READY" if complete(warehouse_count) else "PENDING",
            f"Есть приемка: {warehouse_count} из {run_count}",
            "warehouse-workspace",
        ),
        _stage(
            "erp",
            "Факт ERP",
            "READY" if complete(erp_count) else "PENDING",
            f"Есть ERP-факт: {erp_count} из {run_count}",
            "reconciliation",
        ),
        _stage(
            "reconciliation",
            "Сверка",
            "READY"
            if reconciliation["summary"]["open_cases"] == 0
            and run_count > 0
            else "PENDING",
            (
                "Открытых расхождений нет"
                if reconciliation["summary"]["open_cases"] == 0
                and run_count > 0
                else (
                    "Открытых расхождений: "
                    f"{reconciliation['summary']['open_cases']}"
                )
            ),
            "shift-control",
        ),
        _stage(
            "finish",
            "Закрытие и подтверждение смены",
            "READY" if shift["status"] == "VERIFIED" else "PENDING",
            (
                "Смена VERIFIED"
                if shift["status"] == "VERIFIED"
                else (
                    f"Завершено запусков: {finished_count} из {run_count}; "
                    f"статус смены: {shift['status']}"
                )
            ),
            (
                "production-manager"
                if shift["status"] == "CLOSED"
                else "shift-master"
            ),
        ),
    ]

    completed_steps = sum(
        1 for item in stages if item["status"] == "READY"
    )

    return {
        "shift": shift,
        "summary": {
            "completed_steps": completed_steps,
            "total_steps": len(stages),
            "verified": shift["status"] == "VERIFIED",
            "runs": run_count,
        },
        "stages": stages,
    }
