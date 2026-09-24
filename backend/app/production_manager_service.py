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
