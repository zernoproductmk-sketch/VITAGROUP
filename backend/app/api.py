from fastapi import APIRouter

from .mock_data import DASHBOARD_SUMMARY, DOWNTIME, PAYROLL, RECONCILIATION

router = APIRouter(prefix="/api/v1")


@router.get("/dashboard/summary")
def dashboard_summary():
    return DASHBOARD_SUMMARY


@router.get("/equipment")
def equipment():
    return DASHBOARD_SUMMARY["equipment"]


@router.get("/downtime")
def downtime():
    return DOWNTIME


@router.get("/reconciliation")
def reconciliation():
    return RECONCILIATION


@router.get("/payroll/summary")
def payroll_summary():
    return PAYROLL
