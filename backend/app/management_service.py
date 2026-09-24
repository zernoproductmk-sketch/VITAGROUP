from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .oee_service import current_business_shift
from .production_manager_service import production_manager_day


def _pct(numerator: float, denominator: float):
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _avg(values):
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 1)


def management_overview(
    end_date: date | None = None,
    days: int = 14,
) -> dict:
    if days not in {7, 14, 30}:
        raise ValueError("days must be 7, 14 or 30")

    if end_date is None:
        end_date, _ = current_business_shift()

    start_date = end_date - timedelta(days=days - 1)
    daily = []
    line_accumulator: dict[str, dict] = {}

    totals = {
        "plan": 0.0,
        "output": 0.0,
        "good": 0.0,
        "qc_defect": 0.0,
        "downtime_minutes": 0.0,
        "open_cases": 0,
        "critical_cases": 0,
        "missing_norm_runs": 0,
    }

    cursor = start_date
    while cursor <= end_date:
        day = production_manager_day(cursor)
        summary = day["summary"]

        totals["plan"] += float(summary["plan"] or 0)
        totals["output"] += float(summary["output"] or 0)
        totals["good"] += float(summary["good"] or 0)
        totals["qc_defect"] += float(summary["qc_defect"] or 0)
        totals["downtime_minutes"] += float(summary["downtime_minutes"] or 0)
        totals["open_cases"] += int(summary["open_cases"] or 0)
        totals["critical_cases"] += int(summary["critical_cases"] or 0)
        totals["missing_norm_runs"] += int(summary["missing_norm_runs"] or 0)

        daily.append(
            {
                "business_date": cursor.isoformat(),
                "plan": summary["plan"],
                "output": summary["output"],
                "good": summary["good"],
                "qc_defect": summary["qc_defect"],
                "downtime_minutes": summary["downtime_minutes"],
                "completion_percent": summary["completion_percent"],
                "oee": summary["oee"],
                "open_cases": summary["open_cases"],
                "critical_cases": summary["critical_cases"],
            }
        )

        for row in day["equipment"]:
            acc = line_accumulator.setdefault(
                row["code"],
                {
                    "code": row["code"],
                    "name": row["name"],
                    "plan": 0.0,
                    "output": 0.0,
                    "downtime_minutes": 0.0,
                    "oee_values": [],
                    "problem_shifts": 0,
                    "shifts": 0,
                },
            )

            for shift_key in ("day", "night"):
                item = row.get(shift_key)
                if not item:
                    continue
                acc["shifts"] += 1
                acc["plan"] += float(item.get("plan") or 0)
                acc["output"] += float(item.get("output") or 0)
                acc["downtime_minutes"] += float(
                    item.get("downtime_minutes") or 0
                )
                if item.get("oee") is not None:
                    acc["oee_values"].append(float(item["oee"]))
                if (
                    item.get("state") == "DOWNTIME"
                    or float(item.get("downtime_minutes") or 0) >= 30
                    or (
                        item.get("oee") is not None
                        and float(item["oee"]) < 70
                    )
                    or int(item.get("missing_norm_runs") or 0) > 0
                ):
                    acc["problem_shifts"] += 1

        cursor += timedelta(days=1)

    completion = _pct(totals["output"], totals["plan"])
    defect_rate = _pct(totals["qc_defect"], totals["output"])
    daily_oee = [row["oee"] for row in daily]
    average_oee = _avg(daily_oee)

    first_half = daily[: max(1, len(daily) // 2)]
    second_half = daily[max(1, len(daily) // 2):]

    first_oee = _avg([row["oee"] for row in first_half])
    second_oee = _avg([row["oee"] for row in second_half])
    first_completion = _avg(
        [row["completion_percent"] for row in first_half]
    )
    second_completion = _avg(
        [row["completion_percent"] for row in second_half]
    )

    lines = []
    for acc in line_accumulator.values():
        completion_percent = _pct(acc["output"], acc["plan"])
        average_line_oee = _avg(acc["oee_values"])

        attention_score = 0.0
        attention_score += acc["problem_shifts"] * 10
        attention_score += acc["downtime_minutes"] / 30
        if average_line_oee is not None and average_line_oee < 75:
            attention_score += 75 - average_line_oee
        if completion_percent is not None and completion_percent < 95:
            attention_score += (95 - completion_percent) / 2

        lines.append(
            {
                "code": acc["code"],
                "name": acc["name"],
                "plan": round(acc["plan"], 3),
                "output": round(acc["output"], 3),
                "completion_percent": completion_percent,
                "average_oee": average_line_oee,
                "downtime_minutes": round(
                    acc["downtime_minutes"],
                    1,
                ),
                "problem_shifts": acc["problem_shifts"],
                "shifts": acc["shifts"],
                "attention_score": round(attention_score, 1),
            }
        )

    lines.sort(
        key=lambda item: (
            -item["attention_score"],
            item["code"],
        )
    )

    return {
        "period": {
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "days": days,
        },
        "summary": {
            **{
                key: round(value, 3)
                if isinstance(value, float)
                else value
                for key, value in totals.items()
            },
            "completion_percent": completion,
            "defect_rate_percent": defect_rate,
            "average_oee": average_oee,
        },
        "trend_change": {
            "oee": (
                round(second_oee - first_oee, 1)
                if first_oee is not None and second_oee is not None
                else None
            ),
            "completion": (
                round(second_completion - first_completion, 1)
                if (
                    first_completion is not None
                    and second_completion is not None
                )
                else None
            ),
        },
        "daily": daily,
        "problem_lines": lines[:10],
    }
