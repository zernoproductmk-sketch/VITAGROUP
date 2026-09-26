from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import CurrentUser, require_roles
from .workspace_service import (
    record_accounting_control,
    record_operator_defect,
    record_operator_output,
    record_qc_defect,
    record_qc_no_defect,
    record_warehouse_receipt,
    save_shift_assignment_report,
    start_downtime,
    stop_downtime,
    workspace_context,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["Role workspaces"])


class OperatorOutputInput(BaseModel):
    production_run_id: UUID
    quantity: float = Field(gt=0)
    defect_quantity: float | None = Field(default=None, ge=0)
    occurred_at: datetime | None = None
    comment: str | None = None
    client_event_id: UUID


class OperatorDefectInput(BaseModel):
    production_run_id: UUID
    quantity: float = Field(gt=0)
    reason_id: UUID | None = None
    occurred_at: datetime | None = None
    comment: str | None = None
    client_event_id: UUID


class DowntimeStartInput(BaseModel):
    production_run_id: UUID
    reason_id: UUID | None = None
    started_at: datetime | None = None
    comment: str | None = None
    client_event_id: UUID


class DowntimeStopInput(BaseModel):
    ended_at: datetime | None = None


class QCDefectInput(BaseModel):
    production_run_id: UUID
    quantity: float = Field(gt=0)
    reason_id: UUID | None = None
    occurred_at: datetime | None = None
    comment: str | None = None
    client_event_id: UUID


class QCNoDefectInput(BaseModel):
    production_run_id: UUID
    occurred_at: datetime | None = None
    comment: str | None = None
    client_event_id: UUID


class WarehouseReceiptInput(BaseModel):
    production_run_id: UUID
    quantity: float = Field(gt=0)
    received_at: datetime | None = None
    document_no: str | None = None
    client_event_id: UUID


class AccountingInput(BaseModel):
    production_run_id: UUID
    packages_qty: float = Field(gt=0)
    qty_per_package: float = Field(gt=0)
    observed_at: datetime | None = None
    ticket_no: str | None = None
    comment: str | None = None
    client_event_id: UUID


class ShiftAssignmentReportInput(BaseModel):
    production_run_id: UUID
    report: dict[str, Any]


def _ctx(kind, business_date, shift_code):
    try:
        return workspace_context(kind, business_date, shift_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/operator/context", dependencies=[Depends(require_roles("OPERATOR","ADMIN"))])
def operator_context(business_date: date | None = None, shift_code: str | None = Query(default=None)):
    return _ctx("operator", business_date, shift_code)


@router.post("/operator/output", dependencies=[Depends(require_roles("OPERATOR","ADMIN"))])
def operator_output(payload: OperatorOutputInput, user: CurrentUser):
    try:
        return record_operator_output(
            user, payload.production_run_id, payload.quantity,
            payload.defect_quantity, payload.occurred_at,
            payload.comment, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/operator/defect", dependencies=[Depends(require_roles("OPERATOR","ADMIN"))])
def operator_defect(payload: OperatorDefectInput, user: CurrentUser):
    try:
        return record_operator_defect(
            user, payload.production_run_id, payload.quantity,
            payload.reason_id, payload.occurred_at,
            payload.comment, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/operator/downtime/start", dependencies=[Depends(require_roles("OPERATOR","ADMIN"))])
def downtime_start(payload: DowntimeStartInput, user: CurrentUser):
    try:
        return start_downtime(
            user, payload.production_run_id, payload.reason_id,
            payload.started_at, payload.comment, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/operator/downtime/{downtime_id}/stop",
    dependencies=[Depends(require_roles("OPERATOR","SHIFT_MASTER","PRODUCTION_MANAGER","ADMIN"))],
)
def downtime_stop(downtime_id: UUID, payload: DowntimeStopInput):
    try:
        return stop_downtime(downtime_id, payload.ended_at)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/qc/context", dependencies=[Depends(require_roles("QC","ADMIN"))])
def qc_context(business_date: date | None = None, shift_code: str | None = Query(default=None)):
    return _ctx("qc", business_date, shift_code)


@router.post("/qc/defect", dependencies=[Depends(require_roles("QC","ADMIN"))])
def qc_defect(payload: QCDefectInput, user: CurrentUser):
    try:
        return record_qc_defect(
            user, payload.production_run_id, payload.quantity,
            payload.reason_id, payload.occurred_at,
            payload.comment, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/qc/no-defect", dependencies=[Depends(require_roles("QC","ADMIN"))])
def qc_no_defect(payload: QCNoDefectInput, user: CurrentUser):
    try:
        return record_qc_no_defect(
            user,
            payload.production_run_id,
            payload.occurred_at,
            payload.comment,
            payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/warehouse/context", dependencies=[Depends(require_roles("WAREHOUSE","ADMIN"))])
def warehouse_context(business_date: date | None = None, shift_code: str | None = Query(default=None)):
    return _ctx("warehouse", business_date, shift_code)


@router.post("/warehouse/receipt", dependencies=[Depends(require_roles("WAREHOUSE","ADMIN"))])
def warehouse_receipt(payload: WarehouseReceiptInput, user: CurrentUser):
    try:
        return record_warehouse_receipt(
            user, payload.production_run_id, payload.quantity,
            payload.received_at, payload.document_no, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/accountant/context", dependencies=[Depends(require_roles("ACCOUNTANT_PRODUCTION","ADMIN"))])
def accountant_context(business_date: date | None = None, shift_code: str | None = Query(default=None)):
    return _ctx("accountant", business_date, shift_code)


@router.post("/accountant/control", dependencies=[Depends(require_roles("ACCOUNTANT_PRODUCTION","ADMIN"))])
def accountant_control(payload: AccountingInput, user: CurrentUser):
    try:
        return record_accounting_control(
            user, payload.production_run_id, payload.packages_qty,
            payload.qty_per_package, payload.observed_at,
            payload.ticket_no, payload.comment, payload.client_event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/operator/shift-assignment",
    dependencies=[Depends(require_roles("OPERATOR","SHIFT_MASTER","PRODUCTION_MANAGER","ADMIN"))],
)
def operator_shift_assignment(payload: ShiftAssignmentReportInput, user: CurrentUser):
    try:
        return save_shift_assignment_report(
            user,
            payload.production_run_id,
            payload.report,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
