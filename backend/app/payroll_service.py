from __future__ import annotations

import json
from collections import Counter
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from .database import engine


BASIS_LABELS = {
    "OUTPUT": "Выпуск оператора",
    "QC_GOOD": "Годная продукция после ОТК",
    "WAREHOUSE": "Принято складом",
    "ERP": "Факт ERP",
}


RUNS_SQL = text(
    """
    SELECT
        pr.id,
        pr.shift_id,
        pr.equipment_id,
        pr.product_id,
        pr.production_order_id,
        pr.operation_id,
        pr.status AS run_status,
        s.business_date,
        st.code AS shift_code,
        e.code AS equipment_code,
        e.name AS equipment_name,
        p.code AS product_code,
        p.article AS product_article,
        p.name AS product_name,
        po.order_no,
        ppa.product_type,
        ppa.print_flag,
        ppa.tariff_group,
        ppa.confirmed AS payroll_attributes_confirmed,
        COALESCE(outp.output_qty, 0) AS output_qty,
        COALESCE(defs.qc_defect_qty, 0) AS qc_defect_qty,
        COALESCE(defs.operator_defect_qty, 0) AS operator_defect_qty,
        COALESCE(wh.warehouse_qty, 0) AS warehouse_qty,
        COALESCE(erp.erp_qty, 0) AS erp_qty
    FROM production_runs pr
    JOIN shifts s ON s.id = pr.shift_id
    JOIN shift_types st ON st.id = s.shift_type_id
    JOIN equipment e ON e.id = pr.equipment_id
    JOIN products p ON p.id = pr.product_id
    LEFT JOIN production_orders po ON po.id = pr.production_order_id
    LEFT JOIN product_payroll_attributes ppa ON ppa.product_id = pr.product_id
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
        WHERE poe.production_run_id = pr.id
          AND poe.status <> 'REJECTED'
    ) outp ON true
    LEFT JOIN LATERAL (
        SELECT
            COALESCE(
                sum(de.quantity)
                FILTER (
                    WHERE de.reported_by = 'QC'
                      AND de.is_confirmed = true
                ),
                0
            ) AS qc_defect_qty,
            COALESCE(
                sum(de.quantity)
                FILTER (WHERE de.reported_by = 'OPERATOR'),
                0
            ) AS operator_defect_qty
        FROM defect_events de
        WHERE de.production_run_id = pr.id
    ) defs ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(sum(wr.quantity), 0) AS warehouse_qty
        FROM warehouse_receipts wr
        WHERE wr.production_run_id = pr.id
    ) wh ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(sum(epf.quantity), 0) AS erp_qty
        FROM erp_production_facts epf
        WHERE epf.production_run_id = pr.id
    ) erp ON true
    WHERE s.business_date BETWEEN :date_from AND :date_to
      AND pr.status <> 'CANCELLED'
    ORDER BY s.business_date, st.code, e.code, po.order_no, pr.created_at
    """
)


def _number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _basis_quantity(run: dict, basis: str | None) -> float | None:
    if basis is None:
        return None
    output = _number(run["output_qty"])
    if basis == "OUTPUT":
        return output
    if basis == "QC_GOOD":
        return max(output - _number(run["qc_defect_qty"]), 0.0)
    if basis == "WAREHOUSE":
        return _number(run["warehouse_qty"])
    if basis == "ERP":
        return _number(run["erp_qty"])
    return None


def _normalize(value) -> str | None:
    if value is None:
        return None
    result = str(value).strip().lower().replace("ё", "е")
    return result or None


def _is_general(value) -> bool:
    normalized = _normalize(value)
    return normalized in {None, "все", "all", "любой", "любая", "-"}


def _role_matches(rule_role, employee_position) -> bool:
    role = _normalize(rule_role)
    if role is None:
        return True
    position = _normalize(employee_position)
    if position is None:
        return False
    return role in position or position in role


def _condition(rule_value, actual_value) -> tuple[bool, bool, int]:
    if _is_general(rule_value):
        return True, False, 0
    if actual_value is None or str(actual_value).strip() == "":
        return False, True, 0
    matched = _normalize(rule_value) == _normalize(actual_value)
    return matched, False, 1 if matched else 0


def _assignments(connection, run: dict) -> list[dict]:
    rows = connection.execute(
        text(
            """
            SELECT
                esa.id,
                esa.production_run_id,
                esa.employee_id,
                esa.allocation_factor,
                esa.allocation_confirmed,
                esa.started_at,
                esa.ended_at,
                esa.source_system,
                emp.personnel_number,
                emp.full_name,
                emp.position_name,
                emp.department_name
            FROM employee_shift_assignments esa
            JOIN employees emp ON emp.id = esa.employee_id
            WHERE emp.is_active = true
              AND (
                    esa.production_run_id = :run_id
                    OR (
                        esa.production_run_id IS NULL
                        AND esa.shift_id = :shift_id
                        AND esa.equipment_id = :equipment_id
                    )
                  )
            ORDER BY
                CASE WHEN esa.production_run_id = :run_id THEN 0 ELSE 1 END,
                emp.full_name
            """
        ),
        {
            "run_id": run["id"],
            "shift_id": run["shift_id"],
            "equipment_id": run["equipment_id"],
        },
    ).mappings().all()

    explicit = [dict(row) for row in rows if row["production_run_id"] == run["id"]]
    selected = explicit if explicit else [dict(row) for row in rows]

    by_employee = {}
    for row in selected:
        by_employee.setdefault(str(row["employee_id"]), row)
    return list(by_employee.values())


def _rate_candidates(connection, run: dict, employee: dict) -> list[dict]:
    rows = connection.execute(
        text(
            """
            SELECT *
            FROM payroll_rate_rules
            WHERE is_active = true
              AND valid_from <= :business_date
              AND (valid_to IS NULL OR valid_to >= :business_date)
              AND lower(trim(accrual_type)) = lower('Выпуск')
              AND lower(trim(payment_type)) = lower('сделка')
              AND (
                    equipment_id = :equipment_id
                    OR (
                        equipment_id IS NULL
                        AND upper(trim(coalesce(equipment_external_code,''))) = upper(:equipment_code)
                    )
                  )
              AND lower(trim(unit)) IN ('шт','pcs','piece','pieces')
            ORDER BY valid_from DESC, source_row
            """
        ),
        {
            "business_date": run["business_date"],
            "equipment_id": run["equipment_id"],
            "equipment_code": run["equipment_code"],
        },
    ).mappings().all()

    return [
        dict(row)
        for row in rows
        if _role_matches(row["role_name"], employee.get("position_name"))
    ]


def _select_rate(connection, run: dict, employee: dict) -> dict:
    candidates = _rate_candidates(connection, run, employee)
    if not candidates:
        return {
            "status": "MISSING_RATE",
            "rate": None,
            "rule": None,
            "candidate_count": 0,
        }

    matched = []
    unresolved_specific = False

    for rule in candidates:
        score = 0
        product_match, product_unresolved, product_score = _condition(
            rule["product_type"],
            run.get("product_type"),
        )
        print_match, print_unresolved, print_score = _condition(
            rule["print_flag"],
            run.get("print_flag"),
        )
        group_match, group_unresolved, group_score = _condition(
            rule["tariff_group"],
            run.get("tariff_group"),
        )

        unresolved_specific = unresolved_specific or any(
            (product_unresolved, print_unresolved, group_unresolved)
        )

        if product_match and print_match and group_match:
            score = product_score + print_score + group_score
            matched.append((score, rule))

    if not matched:
        return {
            "status": (
                "MISSING_PRODUCT_ATTRIBUTES"
                if unresolved_specific
                else "MISSING_RATE"
            ),
            "rate": None,
            "rule": None,
            "candidate_count": len(candidates),
        }

    best_score = max(score for score, _ in matched)
    best = [rule for score, rule in matched if score == best_score]

    if len(best) != 1:
        return {
            "status": "AMBIGUOUS_RATE",
            "rate": None,
            "rule": None,
            "candidate_count": len(best),
        }

    rule = best[0]
    return {
        "status": "RATE_FOUND",
        "rate": _number(rule["rate"]),
        "rule": {
            "id": str(rule["id"]),
            "role_name": rule["role_name"],
            "equipment_external_code": rule["equipment_external_code"],
            "product_type": rule["product_type"],
            "print_flag": rule["print_flag"],
            "tariff_group": rule["tariff_group"],
            "unit": rule["unit"],
            "rate": _number(rule["rate"]),
            "valid_from": rule["valid_from"].isoformat(),
            "valid_to": (
                rule["valid_to"].isoformat()
                if rule["valid_to"]
                else None
            ),
        },
        "candidate_count": 1,
    }


def payroll_preview(
    date_from: date,
    date_to: date,
    quantity_basis: str | None = None,
) -> dict:
    if date_to < date_from:
        raise ValueError("date_to must be on or after date_from")
    if quantity_basis is not None and quantity_basis not in BASIS_LABELS:
        raise ValueError("Unsupported quantity basis")

    result_rows = []
    blocker_counts = Counter()
    warning_counts = Counter()

    with engine.begin() as connection:
        runs = [
            dict(row)
            for row in connection.execute(
                RUNS_SQL,
                {"date_from": date_from, "date_to": date_to},
            ).mappings()
        ]

        for run in runs:
            source_quantity = _basis_quantity(run, quantity_basis)
            assignments = _assignments(connection, run)

            if not assignments:
                status = "MISSING_EMPLOYEE"
                blocker_counts[status] += 1
                result_rows.append(
                    _preview_row(
                        run,
                        None,
                        source_quantity,
                        1.0,
                        None,
                        status,
                        quantity_basis,
                    )
                )
                continue

            if len(assignments) == 1:
                allocation_ready = True
                factors = {
                    str(assignments[0]["employee_id"]): 1.0
                }
            else:
                total_factor = sum(
                    _number(item["allocation_factor"])
                    for item in assignments
                )
                allocation_ready = (
                    all(item["allocation_confirmed"] for item in assignments)
                    and abs(total_factor - 1.0) <= 0.0001
                )
                factors = {
                    str(item["employee_id"]): _number(item["allocation_factor"])
                    for item in assignments
                }

            for employee in assignments:
                factor = factors[str(employee["employee_id"])]

                if quantity_basis is None:
                    status = "NEEDS_BASIS"
                    rate_info = None
                elif not allocation_ready:
                    status = "NEEDS_ALLOCATION"
                    rate_info = None
                else:
                    rate_info = _select_rate(connection, run, employee)
                    status = (
                        "READY"
                        if rate_info["status"] == "RATE_FOUND"
                        else rate_info["status"]
                    )

                if status not in {"READY"}:
                    blocker_counts[status] += 1

                if run["run_status"] != "VERIFIED":
                    warning_counts["UNVERIFIED_RUN"] += 1

                result_rows.append(
                    _preview_row(
                        run,
                        employee,
                        source_quantity,
                        factor,
                        rate_info,
                        status,
                        quantity_basis,
                    )
                )

    ready_amount = sum(
        row["amount"] or 0
        for row in result_rows
        if row["status"] == "READY"
    )

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "quantity_basis": quantity_basis,
        "quantity_basis_label": BASIS_LABELS.get(quantity_basis),
        "summary": {
            "runs": len({row["production_run_id"] for row in result_rows}),
            "rows": len(result_rows),
            "ready_rows": sum(1 for row in result_rows if row["status"] == "READY"),
            "blocked_rows": sum(1 for row in result_rows if row["status"] != "READY"),
            "preliminary_rows": sum(
                1 for row in result_rows if row["run_status"] != "VERIFIED"
            ),
            "ready_amount": round(ready_amount, 2),
            "blockers": dict(blocker_counts),
            "warnings": dict(warning_counts),
        },
        "rows": result_rows,
    }


def _preview_row(
    run: dict,
    employee: dict | None,
    source_quantity: float | None,
    allocation_factor: float,
    rate_info: dict | None,
    status: str,
    quantity_basis: str | None,
) -> dict:
    rate = rate_info.get("rate") if rate_info else None
    amount = None
    if status == "READY" and source_quantity is not None and rate is not None:
        amount = round(source_quantity * rate * allocation_factor, 2)

    return {
        "production_run_id": str(run["id"]),
        "shift_id": str(run["shift_id"]),
        "business_date": run["business_date"].isoformat(),
        "shift_code": run["shift_code"],
        "run_status": run["run_status"],
        "operation_id": str(run["operation_id"]) if run["operation_id"] else None,
        "equipment_id": str(run["equipment_id"]),
        "equipment_code": run["equipment_code"],
        "equipment_name": run["equipment_name"],
        "product_id": str(run["product_id"]),
        "product_code": run["product_code"],
        "product_article": run["product_article"],
        "product_name": run["product_name"],
        "order_no": run["order_no"],
        "product_type": run.get("product_type"),
        "print_flag": run.get("print_flag"),
        "tariff_group": run.get("tariff_group"),
        "output_qty": _number(run["output_qty"]),
        "operator_defect_qty": _number(run["operator_defect_qty"]),
        "qc_defect_qty": _number(run["qc_defect_qty"]),
        "qc_good_qty": max(
            _number(run["output_qty"]) - _number(run["qc_defect_qty"]),
            0,
        ),
        "warehouse_qty": _number(run["warehouse_qty"]),
        "erp_qty": _number(run["erp_qty"]),
        "quantity_basis": quantity_basis,
        "source_quantity": source_quantity,
        "employee_id": (
            str(employee["employee_id"]) if employee else None
        ),
        "personnel_number": (
            employee["personnel_number"] if employee else None
        ),
        "employee_name": employee["full_name"] if employee else None,
        "employee_position": employee["position_name"] if employee else None,
        "allocation_factor": allocation_factor,
        "allocation_confirmed": (
            bool(employee["allocation_confirmed"]) if employee else False
        ),
        "rate": rate,
        "rate_rule": rate_info.get("rule") if rate_info else None,
        "rate_candidate_count": (
            rate_info.get("candidate_count") if rate_info else None
        ),
        "amount": amount,
        "status": status,
        "preliminary": run["run_status"] != "VERIFIED",
    }


def list_periods(limit: int = 24) -> list[dict]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    pp.*,
                    COALESCE(sum(pl.amount), 0) AS amount,
                    count(pl.id) AS line_count
                FROM payroll_periods pp
                LEFT JOIN payroll_lines pl
                  ON pl.payroll_period_id = pp.id
                GROUP BY pp.id
                ORDER BY pp.date_from DESC, pp.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def upsert_period(
    date_from: date,
    date_to: date,
    quantity_basis: str | None,
    notes: str | None = None,
) -> dict:
    if date_to < date_from:
        raise ValueError("date_to must be on or after date_from")
    if quantity_basis is not None and quantity_basis not in BASIS_LABELS:
        raise ValueError("Unsupported quantity basis")

    with engine.begin() as connection:
        existing = connection.execute(
            text(
                """
                SELECT *
                FROM payroll_periods
                WHERE date_from = :date_from
                  AND date_to = :date_to
                FOR UPDATE
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().first()

        if existing and existing["status"] in {"APPROVED", "EXPORTED"}:
            raise ValueError("Approved/exported payroll period is locked")

        row = connection.execute(
            text(
                """
                INSERT INTO payroll_periods (
                    date_from,
                    date_to,
                    quantity_basis,
                    notes,
                    status
                ) VALUES (
                    :date_from,
                    :date_to,
                    :quantity_basis,
                    :notes,
                    'DRAFT'
                )
                ON CONFLICT (date_from, date_to)
                DO UPDATE SET
                    quantity_basis = EXCLUDED.quantity_basis,
                    notes = EXCLUDED.notes,
                    status = CASE
                        WHEN payroll_periods.status IN ('APPROVED','EXPORTED')
                        THEN payroll_periods.status
                        ELSE 'DRAFT'
                    END
                RETURNING *
                """
            ),
            {
                "date_from": date_from,
                "date_to": date_to,
                "quantity_basis": quantity_basis,
                "notes": notes,
            },
        ).mappings().one()

    return dict(row)


def calculate_period(period_id: UUID) -> dict:
    with engine.begin() as connection:
        period = connection.execute(
            text(
                """
                SELECT *
                FROM payroll_periods
                WHERE id = :id
                FOR UPDATE
                """
            ),
            {"id": period_id},
        ).mappings().first()

    if not period:
        raise LookupError("Payroll period not found")
    if period["status"] in {"APPROVED", "EXPORTED"}:
        raise ValueError("Approved/exported payroll period is locked")

    preview = payroll_preview(
        period["date_from"],
        period["date_to"],
        period["quantity_basis"],
    )
    if preview["summary"]["blocked_rows"] > 0:
        return {
            "status": "BLOCKED",
            "period_id": str(period_id),
            "summary": preview["summary"],
            "rows": preview["rows"],
        }

    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM payroll_lines WHERE payroll_period_id = :period_id"
            ),
            {"period_id": period_id},
        )

        for row in preview["rows"]:
            connection.execute(
                text(
                    """
                    INSERT INTO payroll_lines (
                        payroll_period_id,
                        employee_id,
                        shift_id,
                        production_run_id,
                        operation_id,
                        approved_quantity,
                        rate_per_unit,
                        allocation_factor,
                        basis,
                        rate_rule_id,
                        quantity_basis,
                        source_quantity,
                        calculation_status,
                        calculation_details
                    ) VALUES (
                        :payroll_period_id,
                        :employee_id,
                        :shift_id,
                        :production_run_id,
                        :operation_id,
                        :approved_quantity,
                        :rate_per_unit,
                        :allocation_factor,
                        :basis,
                        :rate_rule_id,
                        :quantity_basis,
                        :source_quantity,
                        :calculation_status,
                        CAST(:calculation_details AS jsonb)
                    )
                    """
                ),
                {
                    "payroll_period_id": period_id,
                    "employee_id": row["employee_id"],
                    "shift_id": row["shift_id"],
                    "production_run_id": row["production_run_id"],
                    "operation_id": row["operation_id"],
                    "approved_quantity": row["source_quantity"],
                    "rate_per_unit": row["rate"],
                    "allocation_factor": row["allocation_factor"],
                    "basis": BASIS_LABELS[row["quantity_basis"]],
                    "rate_rule_id": row["rate_rule"]["id"],
                    "quantity_basis": row["quantity_basis"],
                    "source_quantity": row["source_quantity"],
                    "calculation_status": (
                        "PRELIMINARY" if row["preliminary"] else "READY"
                    ),
                    "calculation_details": json.dumps(
                        {
                            "equipment_code": row["equipment_code"],
                            "order_no": row["order_no"],
                            "product_article": row["product_article"],
                            "rate_rule": row["rate_rule"],
                            "run_status": row["run_status"],
                        },
                        ensure_ascii=False,
                    ),
                },
            )

        connection.execute(
            text(
                """
                UPDATE payroll_periods
                SET status = 'CALCULATED',
                    calculated_at = now()
                WHERE id = :id
                """
            ),
            {"id": period_id},
        )

    return {
        "status": "CALCULATED",
        "period_id": str(period_id),
        "summary": preview["summary"],
        "rows": preview["rows"],
    }


def save_product_attributes(
    product_id: UUID,
    product_type: str | None,
    print_flag: str | None,
    tariff_group: str | None,
) -> dict:
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM products WHERE id = :id"),
            {"id": product_id},
        ).scalar_one_or_none()
        if not exists:
            raise LookupError("Product not found")

        row = connection.execute(
            text(
                """
                INSERT INTO product_payroll_attributes (
                    product_id,
                    product_type,
                    print_flag,
                    tariff_group,
                    confirmed,
                    source_system
                ) VALUES (
                    :product_id,
                    :product_type,
                    :print_flag,
                    :tariff_group,
                    true,
                    'WEB'
                )
                ON CONFLICT (product_id)
                DO UPDATE SET
                    product_type = EXCLUDED.product_type,
                    print_flag = EXCLUDED.print_flag,
                    tariff_group = EXCLUDED.tariff_group,
                    confirmed = true,
                    source_system = 'WEB',
                    updated_at = now()
                RETURNING *
                """
            ),
            {
                "product_id": product_id,
                "product_type": product_type,
                "print_flag": print_flag,
                "tariff_group": tariff_group,
            },
        ).mappings().one()

    return dict(row)


def rate_options(equipment_id: UUID, business_date: date) -> dict:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    product_type,
                    print_flag,
                    tariff_group,
                    rate,
                    unit
                FROM payroll_rate_rules
                WHERE is_active = true
                  AND equipment_id = :equipment_id
                  AND valid_from <= :business_date
                  AND (valid_to IS NULL OR valid_to >= :business_date)
                  AND lower(trim(accrual_type)) = lower('Выпуск')
                  AND lower(trim(payment_type)) = lower('сделка')
                ORDER BY product_type, print_flag, tariff_group, rate
                """
            ),
            {
                "equipment_id": equipment_id,
                "business_date": business_date,
            },
        ).mappings().all()

    def unique(field):
        result = []
        for row in rows:
            value = row[field]
            if value and value not in result:
                result.append(value)
        return result

    return {
        "product_types": unique("product_type"),
        "print_flags": unique("print_flag"),
        "tariff_groups": unique("tariff_group"),
        "rules": [
            {
                **dict(row),
                "rate": _number(row["rate"]),
            }
            for row in rows
        ],
    }


def save_allocation(run_id: UUID, entries: list[dict]) -> dict:
    if not entries:
        raise ValueError("Allocation entries are required")

    total = sum(float(item["allocation_factor"]) for item in entries)
    if abs(total - 1.0) > 0.0001:
        raise ValueError("Allocation factors must sum to 1")

    with engine.begin() as connection:
        run = connection.execute(
            text(
                """
                SELECT shift_id, equipment_id
                FROM production_runs
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
        if not run:
            raise LookupError("Production run not found")

        for item in entries:
            employee_id = item["employee_id"]
            factor = float(item["allocation_factor"])
            if factor <= 0:
                raise ValueError("Allocation factor must be positive")

            assignment = connection.execute(
                text(
                    """
                    SELECT id
                    FROM employee_shift_assignments
                    WHERE production_run_id = :run_id
                      AND employee_id = :employee_id
                    LIMIT 1
                    """
                ),
                {
                    "run_id": run_id,
                    "employee_id": employee_id,
                },
            ).scalar_one_or_none()

            if not assignment:
                raise LookupError(
                    "Employee assignment for this production run not found"
                )

            connection.execute(
                text(
                    """
                    UPDATE employee_shift_assignments
                    SET allocation_factor = :factor,
                        allocation_confirmed = true
                    WHERE id = :id
                    """
                ),
                {
                    "factor": factor,
                    "id": assignment,
                },
            )

    return {
        "status": "ok",
        "production_run_id": str(run_id),
        "allocation_total": round(total, 6),
    }
