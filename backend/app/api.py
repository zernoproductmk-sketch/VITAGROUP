from datetime import date

from fastapi import APIRouter, HTTPException, Query

from .mock_data import PAYROLL
from .oee_service import (
    downtime_rows,
    oee_dashboard_summary,
    oee_run_rows,
    reconciliation_rows,
)

router = APIRouter(prefix="/api/v1")


def _safe_shift_call(func, business_date, shift_code):
    try:
        return func(business_date, shift_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dashboard/summary")
def dashboard_summary(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    return _safe_shift_call(
        oee_dashboard_summary,
        business_date,
        shift_code,
    )


@router.get("/oee/runs")
def oee_runs(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    return {
        "rows": _safe_shift_call(
            oee_run_rows,
            business_date,
            shift_code,
        )
    }


@router.get("/equipment")
def equipment(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    summary = _safe_shift_call(
        oee_dashboard_summary,
        business_date,
        shift_code,
    )
    return summary["equipment"]


@router.get("/downtime")
def downtime(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    return _safe_shift_call(
        downtime_rows,
        business_date,
        shift_code,
    )


@router.get("/reconciliation")
def reconciliation(
    business_date: date | None = None,
    shift_code: str | None = Query(default=None),
):
    return _safe_shift_call(
        reconciliation_rows,
        business_date,
        shift_code,
    )


@router.get("/payroll/summary")
def payroll_summary():
    return PAYROLL
