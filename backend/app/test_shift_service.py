from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text

from .database import engine
from .shifts import ensure_shift


def _shift_row(connection, business_date: date, shift_code: str):
    return connection.execute(
        text(
            """
            SELECT
                s.id,
                s.status,
                s.business_date,
                s.started_at,
                s.ended_at,
                st.code AS shift_code,
                st.name AS shift_name
            FROM shifts s
            JOIN shift_types st ON st.id = s.shift_type_id
            WHERE s.business_date = :business_date
              AND st.code = :shift_code
            LIMIT 1
            """
        ),
        {
            "business_date": business_date,
            "shift_code": shift_code,
        },
    ).mappings().first()


def test_shift_context(
    business_date: date,
    shift_code: str,
) -> dict:
    shift_code = shift_code.upper()
    if shift_code not in {"DAY", "NIGHT"}:
        raise ValueError("shift_code must be DAY or NIGHT")

    with engine.begin() as connection:
        shift = _shift_row(connection, business_date, shift_code)

        employees = connection.execute(
            text(
                """
                SELECT
                    id,
                    personnel_number,
                    full_name,
                    position_name,
                    department_name
                FROM employees
                WHERE is_active = true
                ORDER BY full_name
                """
            )
        ).mappings().all()

        if not shift:
            return {
                "shift": {
                    "id": None,
                    "business_date": business_date.isoformat(),
                    "shift_code": shift_code,
                    "status": "NOT_CREATED",
                },
                "runs": [],
                "employees": [
                    {
                        **dict(row),
                        "id": str(row["id"]),
                    }
                    for row in employees
                ],
                "summary": {
                    "runs": 0,
                    "with_norm": 0,
                    "with_staff": 0,
                    "ready": False,
                    "blockers": [
                        "Смена еще не создана. Сначала импортируйте и продвиньте план ERP."
                    ],
                },
            }

        rows = connection.execute(
            text(
                """
                SELECT
                    pr.id,
                    pr.status,
                    pr.planned_qty,
                    pr.ideal_rate_per_hour,
                    e.id AS equipment_id,
                    e.code AS equipment_code,
                    e.name AS equipment_name,
                    p.id AS product_id,
                    p.code AS product_code,
                    p.article AS product_article,
                    p.name AS product_name,
                    po.order_no
                FROM production_runs pr
                JOIN equipment e ON e.id = pr.equipment_id
                JOIN products p ON p.id = pr.product_id
                LEFT JOIN production_orders po ON po.id = pr.production_order_id
                WHERE pr.shift_id = :shift_id
                  AND pr.status <> 'CANCELLED'
                ORDER BY e.code, po.order_no, pr.created_at
                """
            ),
            {"shift_id": shift["id"]},
        ).mappings().all()

        assignments = connection.execute(
            text(
                """
                SELECT
                    esa.production_run_id,
                    esa.employee_id,
                    esa.allocation_factor,
                    esa.allocation_confirmed,
                    emp.personnel_number,
                    emp.full_name,
                    emp.position_name
                FROM employee_shift_assignments esa
                JOIN employees emp ON emp.id = esa.employee_id
                WHERE esa.shift_id = :shift_id
                  AND esa.production_run_id IS NOT NULL
                  AND emp.is_active = true
                ORDER BY emp.full_name
                """
            ),
            {"shift_id": shift["id"]},
        ).mappings().all()

    by_run: dict[str, list[dict]] = {}
    for row in assignments:
        key = str(row["production_run_id"])
        by_run.setdefault(key, []).append(
            {
                "employee_id": str(row["employee_id"]),
                "personnel_number": row["personnel_number"],
                "full_name": row["full_name"],
                "position_name": row["position_name"],
                "allocation_factor": float(row["allocation_factor"]),
                "allocation_confirmed": row["allocation_confirmed"],
            }
        )

    result_runs = []
    blockers = []

    for row in rows:
        run_id = str(row["id"])
        staff = by_run.get(run_id, [])
        item = {
            **dict(row),
            "id": run_id,
            "equipment_id": str(row["equipment_id"]),
            "product_id": str(row["product_id"]),
            "planned_qty": float(row["planned_qty"] or 0),
            "ideal_rate_per_hour": (
                float(row["ideal_rate_per_hour"])
                if row["ideal_rate_per_hour"] is not None
                else None
            ),
            "staff": staff,
            "ready": (
                row["ideal_rate_per_hour"] is not None
                and len(staff) > 0
                and float(row["planned_qty"] or 0) > 0
            ),
        }
        result_runs.append(item)

        if row["ideal_rate_per_hour"] is None:
            blockers.append(
                f"{row['equipment_code']}: отсутствует норматив скорости"
            )
        if not staff:
            blockers.append(
                f"{row['equipment_code']}: не назначены сотрудники"
            )
        if float(row["planned_qty"] or 0) <= 0:
            blockers.append(
                f"{row['equipment_code']}: не задан план выпуска"
            )

    if not result_runs:
        blockers.append("Для выбранной смены нет производственных запусков")

    return {
        "shift": {
            "id": str(shift["id"]),
            "business_date": shift["business_date"].isoformat(),
            "shift_code": shift["shift_code"],
            "shift_name": shift["shift_name"],
            "status": shift["status"],
            "started_at": shift["started_at"].isoformat(),
            "ended_at": shift["ended_at"].isoformat(),
        },
        "runs": result_runs,
        "employees": [
            {
                **dict(row),
                "id": str(row["id"]),
            }
            for row in employees
        ],
        "summary": {
            "runs": len(result_runs),
            "with_norm": sum(
                1 for row in result_runs
                if row["ideal_rate_per_hour"] is not None
            ),
            "with_staff": sum(
                1 for row in result_runs
                if row["staff"]
            ),
            "ready": len(blockers) == 0,
            "blockers": blockers,
        },
    }


def assign_run_staff(
    *,
    production_run_id: UUID,
    employee_ids: list[UUID],
    user_id: UUID,
) -> dict:
    if not employee_ids:
        raise ValueError("Нужно выбрать хотя бы одного сотрудника")

    unique_ids = list(dict.fromkeys(employee_ids))
    factor = 1 / len(unique_ids)

    with engine.begin() as connection:
        run = connection.execute(
            text(
                """
                SELECT
                    id,
                    shift_id,
                    equipment_id,
                    status
                FROM production_runs
                WHERE id = :run_id
                  AND status <> 'CANCELLED'
                FOR UPDATE
                """
            ),
            {"run_id": production_run_id},
        ).mappings().first()

        if not run:
            raise LookupError("Производственный запуск не найден")

        active_count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM employees
                WHERE id = ANY(:employee_ids)
                  AND is_active = true
                """
            ),
            {"employee_ids": unique_ids},
        ).scalar_one()

        if active_count != len(unique_ids):
            raise ValueError("Один или несколько сотрудников не найдены или неактивны")

        connection.execute(
            text(
                """
                DELETE FROM employee_shift_assignments
                WHERE production_run_id = :run_id
                  AND source_system = 'WEB'
                  AND employee_id <> ALL(:employee_ids)
                """
            ),
            {
                "run_id": production_run_id,
                "employee_ids": unique_ids,
            },
        )

        for employee_id in unique_ids:
            connection.execute(
                text(
                    """
                    INSERT INTO employee_shift_assignments (
                        shift_id,
                        employee_id,
                        equipment_id,
                        production_run_id,
                        allocation_factor,
                        allocation_confirmed,
                        source_system
                    ) VALUES (
                        :shift_id,
                        :employee_id,
                        :equipment_id,
                        :run_id,
                        :allocation_factor,
                        true,
                        'WEB'
                    )
                    ON CONFLICT (production_run_id, employee_id)
                    WHERE production_run_id IS NOT NULL
                    DO UPDATE SET
                        shift_id = EXCLUDED.shift_id,
                        equipment_id = EXCLUDED.equipment_id,
                        allocation_factor = EXCLUDED.allocation_factor,
                        allocation_confirmed = true,
                        source_system = 'WEB'
                    """
                ),
                {
                    "shift_id": run["shift_id"],
                    "employee_id": employee_id,
                    "equipment_id": run["equipment_id"],
                    "run_id": production_run_id,
                    "allocation_factor": factor,
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
                    new_data,
                    reason
                ) VALUES (
                    'production_runs',
                    :run_id,
                    'UPDATE',
                    :user_id,
                    jsonb_build_object(
                        'assigned_employee_count', :employee_count,
                        'allocation_factor', :allocation_factor
                    ),
                    'Назначение сотрудников на запуск перед тестовой сменой'
                )
                """
            ),
            {
                "run_id": production_run_id,
                "user_id": user_id,
                "employee_count": len(unique_ids),
                "allocation_factor": factor,
            },
        )

    return {
        "status": "ok",
        "production_run_id": str(production_run_id),
        "employee_count": len(unique_ids),
        "allocation_factor": factor,
    }


def create_test_shift(
    *,
    business_date: date,
    shift_code: str,
    user_id: UUID,
) -> dict:
    shift_code = shift_code.upper()
    if shift_code not in {"DAY", "NIGHT"}:
        raise ValueError("shift_code must be DAY or NIGHT")

    with engine.begin() as connection:
        shift_id = ensure_shift(
            connection,
            business_date,
            shift_code,
        )
        if not shift_id:
            raise ValueError("Не удалось создать смену")

        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    table_name,
                    record_id,
                    action,
                    changed_by_user_id,
                    new_data,
                    reason
                ) VALUES (
                    'shifts',
                    :shift_id,
                    'INSERT',
                    :user_id,
                    jsonb_build_object(
                        'business_date', CAST(:business_date AS text),
                        'shift_code', :shift_code,
                        'status', 'OPEN'
                    ),
                    'Подготовка тестовой производственной смены'
                )
                """
            ),
            {
                "shift_id": shift_id,
                "user_id": user_id,
                "business_date": business_date,
                "shift_code": shift_code,
            },
        )

    return {
        "status": "OPEN",
        "shift_id": str(shift_id),
        "business_date": business_date.isoformat(),
        "shift_code": shift_code,
    }
