from __future__ import annotations

from datetime import date

from .oee_service import oee_dashboard_summary
from .reconciliation_service import shift_reconciliation


def _shift_block(business_date: date, shift_code: str) -> dict:
    dashboard = oee_dashboard_summary(
        business_date,
        shift_code,
    )
    reconciliation = shift_reconciliation(
        business_date,
        shift_code,
    )

    return {
        "shift": dashboard["shift"],
        "status": dashboard["status"],
        "kpi": dashboard["kpi"],
        "production": dashboard["production"],
        "time": dashboard["time"],
        "data_quality": dashboard["data_quality"],
        "equipment": dashboard["equipment"],
        "reconciliation": reconciliation["summary"],
    }


def production_manager_day(
    business_date: date,
) -> dict:
    day = _shift_block(business_date, "DAY")
    night = _shift_block(business_date, "NIGHT")
    shifts = [day, night]

    total_plan = sum(
        float(item["production"]["plan"] or 0)
        for item in shifts
    )
    total_output = sum(
        float(item["production"]["operator_output"] or 0)
        for item in shifts
    )
    total_good = sum(
        float(item["production"]["good_product"] or 0)
        for item in shifts
    )
    total_qc_defect = sum(
        float(item["production"]["qc_defect"] or 0)
        for item in shifts
    )
    total_downtime = sum(
        float(item["time"]["downtime_minutes"] or 0)
        for item in shifts
    )

    weighted_oee_numerator = 0.0
    weighted_oee_denominator = 0.0
    for item in shifts:
        oee = item["kpi"]["oee"]
        runtime = float(item["time"]["planned_minutes"] or 0)
        if oee is not None and runtime > 0:
            weighted_oee_numerator += float(oee) * runtime
            weighted_oee_denominator += runtime

    daily_oee = (
        round(
            weighted_oee_numerator / weighted_oee_denominator,
            1,
        )
        if weighted_oee_denominator > 0
        else None
    )

    equipment = {}
    for item in shifts:
        shift_code = item["shift"]["type"]
        for line in item["equipment"]:
            key = line["code"]
            equipment.setdefault(
                key,
                {
                    "code": line["code"],
                    "name": line["name"],
                    "day": None,
                    "night": None,
                },
            )
            equipment[key][shift_code.lower()] = line

    return {
        "business_date": business_date.isoformat(),
        "summary": {
            "plan": round(total_plan, 3),
            "output": round(total_output, 3),
            "good": round(total_good, 3),
            "qc_defect": round(total_qc_defect, 3),
            "downtime_minutes": round(total_downtime, 1),
            "completion_percent": (
                round(total_output / total_plan * 100, 1)
                if total_plan > 0
                else None
            ),
            "oee": daily_oee,
            "open_cases": sum(
                item["reconciliation"]["open_cases"]
                for item in shifts
            ),
            "critical_cases": sum(
                item["reconciliation"]["critical"]
                for item in shifts
            ),
            "missing_norm_runs": sum(
                item["data_quality"]["missing_norm_runs"]
                for item in shifts
            ),
        },
        "day": day,
        "night": night,
        "equipment": sorted(
            equipment.values(),
            key=lambda row: row["code"],
        ),
    }


from uuid import UUID
from sqlalchemy import text
from .database import engine


def verify_shift(
    business_date: date,
    shift_code: str,
    user_id: UUID,
) -> dict:
    block = _shift_block(business_date, shift_code)
    shift_id = block["shift"].get("id")
    if not shift_id:
        raise LookupError("Смена не найдена")

    if block["status"] not in {"CLOSED", "VERIFIED"}:
        raise ValueError(
            "Сначала смена должна быть закрыта сменным мастером"
        )

    if block["reconciliation"]["open_cases"] > 0:
        raise ValueError(
            "Нельзя подтвердить смену: есть незакрытые расхождения"
        )

    if block["data_quality"]["missing_norm_runs"] > 0:
        raise ValueError(
            "Нельзя подтвердить смену: есть запуски без норматива скорости"
        )

    with engine.begin() as connection:
        shift = connection.execute(
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

        if not shift:
            raise LookupError("Смена не найдена")

        if shift["status"] == "VERIFIED":
            return {
                "status": "VERIFIED",
                "shift_id": shift_id,
                "already_verified": True,
            }

        unfinished = connection.execute(
            text(
                """
                SELECT count(*)
                FROM production_runs
                WHERE shift_id = :shift_id
                  AND status NOT IN ('COMPLETED','VERIFIED','CANCELLED')
                """
            ),
            {"shift_id": UUID(shift_id)},
        ).scalar_one()

        if unfinished:
            raise ValueError(
                f"Есть незавершенные производственные запуски: {unfinished}"
            )

        connection.execute(
            text(
                """
                UPDATE production_runs
                SET status = 'VERIFIED',
                    updated_at = now()
                WHERE shift_id = :shift_id
                  AND status = 'COMPLETED'
                """
            ),
            {"shift_id": UUID(shift_id)},
        )

        connection.execute(
            text(
                """
                UPDATE shifts
                SET status = 'VERIFIED'
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
                    'VERIFY',
                    :user_id,
                    jsonb_build_object('status', :old_status),
                    jsonb_build_object('status', 'VERIFIED'),
                    'Верификация смены руководителем производства'
                )
                """
            ),
            {
                "shift_id": UUID(shift_id),
                "user_id": user_id,
                "old_status": shift["status"],
            },
        )

    return {
        "status": "VERIFIED",
        "shift_id": shift_id,
        "already_verified": False,
    }
