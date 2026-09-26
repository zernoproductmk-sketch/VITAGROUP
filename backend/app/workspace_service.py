from __future__ import annotations

import json

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings
from .database import engine
from .oee_service import current_business_shift


def _num(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _target(business_date: date | None, shift_code: str | None):
    current_date, current_shift = current_business_shift()
    business_date = business_date or current_date
    shift_code = (shift_code or current_shift).upper()
    if shift_code not in {"DAY", "NIGHT"}:
        raise ValueError("shift_code must be DAY or NIGHT")
    return business_date, shift_code


def _bounds(business_date: date, shift_code: str):
    tz = ZoneInfo(settings.business_timezone)
    if shift_code == "DAY":
        return (
            datetime.combine(business_date, time(9, 0), tzinfo=tz),
            datetime.combine(business_date, time(21, 0), tzinfo=tz),
        )
    return (
        datetime.combine(business_date, time(21, 0), tzinfo=tz),
        datetime.combine(business_date + timedelta(days=1), time(9, 0), tzinfo=tz),
    )


def _local_dt(value: datetime | None):
    tz = ZoneInfo(settings.business_timezone)
    if value is None:
        return datetime.now(tz)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _load_run(connection, run_id: UUID):
    row = connection.execute(
        text("""
            SELECT
                pr.id,
                pr.shift_id,
                pr.equipment_id,
                pr.product_id,
                pr.status,
                s.started_at AS shift_started_at,
                s.ended_at AS shift_ended_at
            FROM production_runs pr
            JOIN shifts s ON s.id = pr.shift_id
            WHERE pr.id = :run_id
              AND pr.status <> 'CANCELLED'
        """),
        {"run_id": run_id},
    ).mappings().first()
    if not row:
        raise LookupError("Производственный запуск не найден")
    return dict(row)


def _checked_time(run: dict, value: datetime | None):
    event_at = _local_dt(value)
    if event_at < run["shift_started_at"] or event_at > run["shift_ended_at"]:
        raise ValueError("Время события должно находиться внутри выбранной смены")
    return event_at


def workspace_context(workspace: str, business_date=None, shift_code=None):
    business_date, shift_code = _target(business_date, shift_code)
    shift_start, shift_end = _bounds(business_date, shift_code)

    with engine.begin() as connection:
        runs = connection.execute(
            text("""
                SELECT
                    pr.id,
                    pr.status,
                    pr.planned_qty,
                    s.id AS shift_id,
                    e.id AS equipment_id,
                    e.code AS equipment_code,
                    e.name AS equipment_name,
                    p.id AS product_id,
                    p.code AS product_code,
                    p.article AS product_article,
                    p.name AS product_name,
                    po.order_no,
                    eps.task_id AS erp_task_id,
                    eps.customer AS erp_customer,
                    eps.tech_card AS erp_tech_card,
                    eps.plan_kg AS erp_plan_kg,
                    eps.pcs_per_box AS erp_pcs_per_box,
                    eps.boxes_per_pallet AS erp_boxes_per_pallet,
                    eps.norm_hours AS erp_norm_hours,
                    eps.raw_data AS erp_raw_data,
                    pr.shift_assignment_report,
                    pr.shift_assignment_report_updated_at,
                    COALESCE(outp.output_qty, 0) AS output_qty,
                    COALESCE(defs.operator_defect_qty, 0) AS operator_defect_qty,
                    COALESCE(defs.qc_defect_qty, 0) AS qc_defect_qty,
                    COALESCE(wh.warehouse_qty, 0) AS warehouse_qty,
                    COALESCE(acc.accounting_qty, 0) AS accounting_qty
                FROM production_runs pr
                JOIN shifts s ON s.id = pr.shift_id
                JOIN shift_types st ON st.id = s.shift_type_id
                JOIN equipment e ON e.id = pr.equipment_id
                JOIN products p ON p.id = pr.product_id
                LEFT JOIN production_orders po ON po.id = pr.production_order_id
                LEFT JOIN LATERAL (
                    SELECT
                        task_id,
                        customer,
                        tech_card,
                        plan_kg,
                        pcs_per_box,
                        boxes_per_pallet,
                        norm_hours,
                        raw_data
                    FROM erp_plan_staging eps0
                    WHERE eps0.production_run_id = pr.id
                    ORDER BY eps0.updated_at DESC, eps0.created_at DESC
                    LIMIT 1
                ) eps ON true
                LEFT JOIN LATERAL (
                    SELECT
                        CASE
                            WHEN count(*) FILTER (WHERE event_kind = 'FINAL') > 0
                            THEN (
                                array_agg(quantity ORDER BY occurred_at DESC, created_at DESC)
                                FILTER (WHERE event_kind = 'FINAL')
                            )[1]
                            ELSE COALESCE(
                                sum(quantity)
                                FILTER (WHERE event_kind IN ('INCREMENT','CORRECTION')),
                                0
                            )
                        END AS output_qty
                    FROM production_output_events
                    WHERE production_run_id = pr.id
                      AND status <> 'REJECTED'
                ) outp ON true
                LEFT JOIN LATERAL (
                    SELECT
                        COALESCE(sum(quantity) FILTER (WHERE reported_by = 'OPERATOR'), 0)
                            AS operator_defect_qty,
                        COALESCE(
                            sum(quantity)
                            FILTER (WHERE reported_by = 'QC' AND is_confirmed = true),
                            0
                        ) AS qc_defect_qty
                    FROM defect_events
                    WHERE production_run_id = pr.id
                ) defs ON true
                LEFT JOIN LATERAL (
                    SELECT COALESCE(sum(quantity), 0) AS warehouse_qty
                    FROM warehouse_receipts
                    WHERE production_run_id = pr.id
                ) wh ON true
                LEFT JOIN LATERAL (
                    SELECT COALESCE(sum(quantity), 0) AS accounting_qty
                    FROM accounting_control_events
                    WHERE production_run_id = pr.id
                ) acc ON true
                WHERE s.business_date = :business_date
                  AND st.code = :shift_code
                  AND pr.status <> 'CANCELLED'
                ORDER BY e.code, po.order_no, pr.created_at
            """),
            {"business_date": business_date, "shift_code": shift_code},
        ).mappings().all()

        downtime_reasons = [
            {**dict(r), "id": str(r["id"])}
            for r in connection.execute(
                text("""
                    SELECT id, code, name, is_planned
                    FROM downtime_reasons
                    WHERE is_active = true
                    ORDER BY category, name
                """)
            ).mappings()
        ]

        defect_reasons = [
            {**dict(r), "id": str(r["id"])}
            for r in connection.execute(
                text("""
                    SELECT id, code, name
                    FROM defect_reasons
                    WHERE is_active = true
                    ORDER BY category NULLS LAST, name
                """)
            ).mappings()
        ]

        active_downtime = [
            {
                **dict(r),
                "id": str(r["id"]),
                "production_run_id": str(r["production_run_id"]) if r["production_run_id"] else None,
                "started_at": r["started_at"].isoformat(),
            }
            for r in connection.execute(
                text("""
                    SELECT
                        d.id,
                        d.production_run_id,
                        d.started_at,
                        COALESCE(dr.name, d.comment, 'Простой') AS reason,
                        e.code AS equipment_code
                    FROM downtime_events d
                    JOIN shifts s ON s.id = d.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    JOIN equipment e ON e.id = d.equipment_id
                    LEFT JOIN downtime_reasons dr ON dr.id = d.reason_id
                    WHERE s.business_date = :business_date
                      AND st.code = :shift_code
                      AND d.ended_at IS NULL
                    ORDER BY d.started_at
                """),
                {"business_date": business_date, "shift_code": shift_code},
            ).mappings()
        ]


        if workspace == "operator":
            recent_rows = connection.execute(
                text("""
                    SELECT
                        poe.id,
                        poe.occurred_at AS event_at,
                        'Выпуск' AS event_type,
                        poe.quantity,
                        e.code AS equipment_code,
                        p.name AS product_name,
                        po.order_no,
                        poe.comment
                    FROM production_output_events poe
                    JOIN production_runs pr ON pr.id = poe.production_run_id
                    JOIN equipment e ON e.id = pr.equipment_id
                    JOIN products p ON p.id = pr.product_id
                    LEFT JOIN production_orders po ON po.id = pr.production_order_id
                    JOIN shifts s ON s.id = pr.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    WHERE poe.source_system = 'WEB'
                      AND s.business_date = :business_date
                      AND st.code = :shift_code
                    UNION ALL
                    SELECT
                        de.id,
                        de.occurred_at AS event_at,
                        'Брак' AS event_type,
                        de.quantity,
                        e.code AS equipment_code,
                        p.name AS product_name,
                        po.order_no,
                        de.comment
                    FROM defect_events de
                    JOIN production_runs pr ON pr.id = de.production_run_id
                    JOIN equipment e ON e.id = pr.equipment_id
                    JOIN products p ON p.id = pr.product_id
                    LEFT JOIN production_orders po ON po.id = pr.production_order_id
                    JOIN shifts s ON s.id = pr.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    WHERE de.source_system = 'WEB'
                      AND de.reported_by = 'OPERATOR'
                      AND s.business_date = :business_date
                      AND st.code = :shift_code
                    ORDER BY event_at DESC
                    LIMIT 50
                """),
                {"business_date": business_date, "shift_code": shift_code},
            ).mappings().all()
        elif workspace == "qc":
            recent_rows = connection.execute(
                text("""
                    SELECT
                        qi.id,
                        qi.checked_at AS event_at,
                        CASE
                            WHEN qi.result = 'NO_DEFECT'
                            THEN 'ОТК — без брака'
                            ELSE 'Брак ОТК'
                        END AS event_type,
                        qi.defect_quantity AS quantity,
                        e.code AS equipment_code,
                        p.name AS product_name,
                        po.order_no,
                        qi.comment
                    FROM qc_inspections qi
                    JOIN production_runs pr ON pr.id = qi.production_run_id
                    JOIN equipment e ON e.id = pr.equipment_id
                    JOIN products p ON p.id = pr.product_id
                    LEFT JOIN production_orders po ON po.id = pr.production_order_id
                    JOIN shifts s ON s.id = pr.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    WHERE qi.source_system = 'WEB'
                      AND s.business_date = :business_date
                      AND st.code = :shift_code
                    ORDER BY qi.checked_at DESC
                    LIMIT 50
                """),
                {"business_date": business_date, "shift_code": shift_code},
            ).mappings().all()
        elif workspace == "warehouse":
            recent_rows = connection.execute(
                text("""
                    SELECT
                        wr.id,
                        wr.received_at AS event_at,
                        'Приемка' AS event_type,
                        wr.quantity,
                        e.code AS equipment_code,
                        p.name AS product_name,
                        po.order_no,
                        wr.warehouse_document_no AS comment
                    FROM warehouse_receipts wr
                    LEFT JOIN production_runs pr ON pr.id = wr.production_run_id
                    LEFT JOIN equipment e ON e.id = pr.equipment_id
                    JOIN products p ON p.id = wr.product_id
                    LEFT JOIN production_orders po ON po.id = pr.production_order_id
                    JOIN shifts s ON s.id = wr.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    WHERE wr.source_system = 'WEB'
                      AND s.business_date = :business_date
                      AND st.code = :shift_code
                    ORDER BY wr.received_at DESC
                    LIMIT 50
                """),
                {"business_date": business_date, "shift_code": shift_code},
            ).mappings().all()
        else:
            recent_rows = connection.execute(
                text("""
                    SELECT
                        a.id,
                        a.observed_at AS event_at,
                        'Учетчик' AS event_type,
                        a.quantity,
                        e.code AS equipment_code,
                        p.name AS product_name,
                        po.order_no,
                        a.ticket_no AS comment
                    FROM accounting_control_events a
                    LEFT JOIN production_runs pr ON pr.id = a.production_run_id
                    LEFT JOIN equipment e ON e.id = a.equipment_id
                    JOIN products p ON p.id = a.product_id
                    LEFT JOIN production_orders po ON po.id = pr.production_order_id
                    JOIN shifts s ON s.id = a.shift_id
                    JOIN shift_types st ON st.id = s.shift_type_id
                    WHERE s.business_date = :business_date
                      AND st.code = :shift_code
                    ORDER BY a.observed_at DESC
                    LIMIT 50
                """),
                {"business_date": business_date, "shift_code": shift_code},
            ).mappings().all()

        recent = [
            {
                **dict(r),
                "id": str(r["id"]),
                "event_at": r["event_at"].isoformat(),
                "quantity": _num(r["quantity"]),
            }
            for r in recent_rows
        ]

    return {
        "workspace": workspace,
        "shift": {
            "business_date": business_date.isoformat(),
            "code": shift_code,
            "label": "ДЕНЬ" if shift_code == "DAY" else "НОЧЬ",
            "time": "09:00–21:00" if shift_code == "DAY" else "21:00–09:00",
            "started_at": shift_start.isoformat(),
            "ended_at": shift_end.isoformat(),
        },
        "runs": [
            {
                **dict(r),
                "id": str(r["id"]),
                "shift_id": str(r["shift_id"]),
                "equipment_id": str(r["equipment_id"]),
                "product_id": str(r["product_id"]),
                "planned_qty": _num(r["planned_qty"]),
                "output_qty": _num(r["output_qty"]),
                "operator_defect_qty": _num(r["operator_defect_qty"]),
                "qc_defect_qty": _num(r["qc_defect_qty"]),
                "warehouse_qty": _num(r["warehouse_qty"]),
                "accounting_qty": _num(r["accounting_qty"]),
                "erp_plan_kg": _num(r["erp_plan_kg"]),
                "erp_pcs_per_box": _num(r["erp_pcs_per_box"]),
                "erp_boxes_per_pallet": _num(r["erp_boxes_per_pallet"]),
                "erp_norm_hours": _num(r["erp_norm_hours"]),
                "shift_assignment_report": r["shift_assignment_report"] or {},
                "shift_assignment_report_updated_at": (
                    r["shift_assignment_report_updated_at"].isoformat()
                    if r["shift_assignment_report_updated_at"] else None
                ),
            }
            for r in runs
        ],
        "downtime_reasons": downtime_reasons,
        "defect_reasons": defect_reasons,
        "active_downtime": active_downtime,
        "recent": recent,
    }


def record_operator_output(user, run_id, quantity, defect_quantity, occurred_at, comment, client_event_id):
    if quantity <= 0:
        raise ValueError("Количество выпуска должно быть больше нуля")

    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, occurred_at)
        source_id = f"WEB:{client_event_id}"

        output_id = connection.execute(
            text("""
                INSERT INTO production_output_events (
                    production_run_id, occurred_at, quantity, event_kind, status,
                    source_system, source_record_id, entered_by_user_id, comment
                ) VALUES (
                    :run_id, :event_at, :quantity, 'INCREMENT', 'RECORDED',
                    'WEB', :source_id, :user_id, :comment
                )
                ON CONFLICT (source_system, source_record_id)
                WHERE source_record_id IS NOT NULL
                DO UPDATE SET
                    occurred_at = EXCLUDED.occurred_at,
                    quantity = EXCLUDED.quantity,
                    comment = EXCLUDED.comment
                RETURNING id
            """),
            {
                "run_id": run_id,
                "event_at": event_at,
                "quantity": quantity,
                "source_id": source_id,
                "user_id": UUID(user["id"]),
                "comment": comment,
            },
        ).scalar_one()

        if defect_quantity and defect_quantity > 0:
            connection.execute(
                text("""
                    INSERT INTO defect_events (
                        production_run_id, occurred_at, quantity, reported_by,
                        is_confirmed, source_system, source_record_id,
                        entered_by_user_id, comment
                    ) VALUES (
                        :run_id, :event_at, :quantity, 'OPERATOR',
                        false, 'WEB', :source_id, :user_id, :comment
                    )
                    ON CONFLICT (source_system, source_record_id)
                    WHERE source_record_id IS NOT NULL
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        occurred_at = EXCLUDED.occurred_at,
                        comment = EXCLUDED.comment
                """),
                {
                    "run_id": run_id,
                    "event_at": event_at,
                    "quantity": defect_quantity,
                    "source_id": f"{source_id}:DEFECT",
                    "user_id": UUID(user["id"]),
                    "comment": comment,
                },
            )

        connection.execute(
            text("""
                UPDATE production_runs
                SET actual_start_at = CASE
                        WHEN actual_start_at IS NULL THEN :event_at
                        ELSE LEAST(actual_start_at, :event_at)
                    END,
                    status = CASE
                        WHEN status IN ('VERIFIED','COMPLETED') THEN status
                        ELSE 'RUNNING'
                    END,
                    updated_at = now()
                WHERE id = :run_id
            """),
            {"event_at": event_at, "run_id": run_id},
        )

    return {"status": "ok", "event_id": str(output_id), "occurred_at": event_at.isoformat()}


def start_downtime(user, run_id, reason_id, started_at, comment, client_event_id):
    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, started_at)

        existing = connection.execute(
            text("""
                SELECT id
                FROM downtime_events
                WHERE equipment_id = :equipment_id
                  AND shift_id = :shift_id
                  AND ended_at IS NULL
                LIMIT 1
            """),
            {"equipment_id": run["equipment_id"], "shift_id": run["shift_id"]},
        ).scalar_one_or_none()
        if existing:
            raise ValueError("По этой линии уже есть активный простой")

        downtime_id = connection.execute(
            text("""
                INSERT INTO downtime_events (
                    production_run_id, equipment_id, shift_id, reason_id,
                    started_at, is_planned, source_system, source_record_id,
                    entered_by_user_id, comment
                )
                SELECT
                    :run_id, :equipment_id, :shift_id, :reason_id,
                    :event_at, COALESCE(dr.is_planned, false),
                    'WEB', :source_id, :user_id, :comment
                FROM (SELECT 1) x
                LEFT JOIN downtime_reasons dr ON dr.id = :reason_id
                RETURNING id
            """),
            {
                "run_id": run_id,
                "equipment_id": run["equipment_id"],
                "shift_id": run["shift_id"],
                "reason_id": reason_id,
                "event_at": event_at,
                "source_id": f"WEB:{client_event_id}",
                "user_id": UUID(user["id"]),
                "comment": comment,
            },
        ).scalar_one()

        connection.execute(
            text("""
                UPDATE production_runs
                SET status = CASE WHEN status = 'VERIFIED' THEN status ELSE 'PAUSED' END,
                    updated_at = now()
                WHERE id = :run_id
            """),
            {"run_id": run_id},
        )

    return {"status": "ok", "downtime_id": str(downtime_id), "started_at": event_at.isoformat()}


def stop_downtime(downtime_id, ended_at):
    event_at = _local_dt(ended_at)
    with engine.begin() as connection:
        row = connection.execute(
            text("""
                SELECT id, production_run_id, started_at, ended_at
                FROM downtime_events
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": downtime_id},
        ).mappings().first()
        if not row:
            raise LookupError("Простой не найден")
        if row["ended_at"]:
            return {"status": "ok", "downtime_id": str(downtime_id)}
        if event_at <= row["started_at"]:
            raise ValueError("Окончание простоя должно быть позже начала")

        connection.execute(
            text("UPDATE downtime_events SET ended_at = :ended_at WHERE id = :id"),
            {"ended_at": event_at, "id": downtime_id},
        )
        if row["production_run_id"]:
            connection.execute(
                text("""
                    UPDATE production_runs
                    SET status = CASE WHEN status = 'PAUSED' THEN 'RUNNING' ELSE status END,
                        updated_at = now()
                    WHERE id = :run_id
                """),
                {"run_id": row["production_run_id"]},
            )

    return {"status": "ok", "downtime_id": str(downtime_id), "ended_at": event_at.isoformat()}


def _record_qc_inspection(
    connection,
    *,
    run_id,
    checked_at,
    result,
    defect_quantity,
    user_id,
    comment,
    source_id,
):
    return connection.execute(
        text(
            """
            INSERT INTO qc_inspections (
                production_run_id,
                checked_at,
                result,
                defect_quantity,
                source_system,
                source_record_id,
                entered_by_user_id,
                comment
            ) VALUES (
                :run_id,
                :checked_at,
                :result,
                :defect_quantity,
                'WEB',
                :source_id,
                :user_id,
                :comment
            )
            ON CONFLICT (source_system, source_record_id)
            WHERE source_record_id IS NOT NULL
            DO UPDATE SET
                checked_at = EXCLUDED.checked_at,
                result = EXCLUDED.result,
                defect_quantity = EXCLUDED.defect_quantity,
                comment = EXCLUDED.comment
            RETURNING id
            """
        ),
        {
            "run_id": run_id,
            "checked_at": checked_at,
            "result": result,
            "defect_quantity": defect_quantity,
            "source_id": source_id,
            "user_id": user_id,
            "comment": comment,
        },
    ).scalar_one()


def record_qc_no_defect(
    user,
    run_id,
    occurred_at,
    comment,
    client_event_id,
):
    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, occurred_at)
        inspection_id = _record_qc_inspection(
            connection,
            run_id=run_id,
            checked_at=event_at,
            result="NO_DEFECT",
            defect_quantity=0,
            user_id=UUID(user["id"]),
            comment=comment,
            source_id=f"WEB:{client_event_id}",
        )

    return {
        "status": "ok",
        "inspection_id": str(inspection_id),
        "occurred_at": event_at.isoformat(),
        "result": "NO_DEFECT",
    }


def record_qc_defect(user, run_id, quantity, reason_id, occurred_at, comment, client_event_id):
    if quantity <= 0:
        raise ValueError("Количество брака должно быть больше нуля")

    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, occurred_at)
        event_id = connection.execute(
            text("""
                INSERT INTO defect_events (
                    production_run_id, occurred_at, quantity, defect_reason_id,
                    reported_by, is_confirmed, source_system, source_record_id,
                    entered_by_user_id, comment
                ) VALUES (
                    :run_id, :event_at, :quantity, :reason_id,
                    'QC', true, 'WEB', :source_id, :user_id, :comment
                )
                ON CONFLICT (source_system, source_record_id)
                WHERE source_record_id IS NOT NULL
                DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    defect_reason_id = EXCLUDED.defect_reason_id,
                    occurred_at = EXCLUDED.occurred_at,
                    comment = EXCLUDED.comment
                RETURNING id
            """),
            {
                "run_id": run_id,
                "event_at": event_at,
                "quantity": quantity,
                "reason_id": reason_id,
                "source_id": f"WEB:{client_event_id}",
                "user_id": UUID(user["id"]),
                "comment": comment,
            },
        ).scalar_one()

        _record_qc_inspection(
            connection,
            run_id=run_id,
            checked_at=event_at,
            result="DEFECT_RECORDED",
            defect_quantity=quantity,
            user_id=UUID(user["id"]),
            comment=comment,
            source_id=f"WEB:{client_event_id}:CHECK",
        )

    return {"status": "ok", "event_id": str(event_id), "occurred_at": event_at.isoformat()}


def record_warehouse_receipt(user, run_id, quantity, received_at, document_no, client_event_id):
    if quantity <= 0:
        raise ValueError("Количество приемки должно быть больше нуля")

    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, received_at)
        receipt_id = connection.execute(
            text("""
                INSERT INTO warehouse_receipts (
                    production_run_id, shift_id, product_id, received_at,
                    quantity, warehouse_document_no, source_system,
                    source_record_id, entered_by_user_id
                ) VALUES (
                    :run_id, :shift_id, :product_id, :event_at,
                    :quantity, :document_no, 'WEB', :source_id, :user_id
                )
                ON CONFLICT (source_system, source_record_id)
                WHERE source_record_id IS NOT NULL
                DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    received_at = EXCLUDED.received_at,
                    warehouse_document_no = EXCLUDED.warehouse_document_no
                RETURNING id
            """),
            {
                "run_id": run_id,
                "shift_id": run["shift_id"],
                "product_id": run["product_id"],
                "event_at": event_at,
                "quantity": quantity,
                "document_no": document_no,
                "source_id": f"WEB:{client_event_id}",
                "user_id": UUID(user["id"]),
            },
        ).scalar_one()

    return {"status": "ok", "receipt_id": str(receipt_id), "received_at": event_at.isoformat()}


def record_accounting_control(user, run_id, packages_qty, qty_per_package, observed_at, ticket_no, comment, client_event_id):
    if packages_qty <= 0 or qty_per_package <= 0:
        raise ValueError("Количество упаковок и количество в упаковке должны быть больше нуля")

    quantity = packages_qty * qty_per_package

    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, observed_at)
        event_id = connection.execute(
            text("""
                INSERT INTO accounting_control_events (
                    production_run_id, shift_id, equipment_id, product_id,
                    observed_at, ticket_no, packages_qty, qty_per_package,
                    quantity, source_system, source_record_id,
                    entered_by_user_id, comment
                ) VALUES (
                    :run_id, :shift_id, :equipment_id, :product_id,
                    :event_at, :ticket_no, :packages_qty, :qty_per_package,
                    :quantity, 'WEB', :source_id, :user_id, :comment
                )
                ON CONFLICT (source_system, source_record_id)
                WHERE source_record_id IS NOT NULL
                DO UPDATE SET
                    observed_at = EXCLUDED.observed_at,
                    ticket_no = EXCLUDED.ticket_no,
                    packages_qty = EXCLUDED.packages_qty,
                    qty_per_package = EXCLUDED.qty_per_package,
                    quantity = EXCLUDED.quantity,
                    comment = EXCLUDED.comment
                RETURNING id
            """),
            {
                "run_id": run_id,
                "shift_id": run["shift_id"],
                "equipment_id": run["equipment_id"],
                "product_id": run["product_id"],
                "event_at": event_at,
                "ticket_no": ticket_no,
                "packages_qty": packages_qty,
                "qty_per_package": qty_per_package,
                "quantity": quantity,
                "source_id": f"WEB:{client_event_id}",
                "user_id": UUID(user["id"]),
                "comment": comment,
            },
        ).scalar_one()

    return {"status": "ok", "event_id": str(event_id), "quantity": quantity}


def record_operator_defect(user, run_id, quantity, reason_id, occurred_at, comment, client_event_id):
    if quantity <= 0:
        raise ValueError("Количество брака должно быть больше нуля")

    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        event_at = _checked_time(run, occurred_at)
        event_id = connection.execute(
            text("""
                INSERT INTO defect_events (
                    production_run_id, occurred_at, quantity, defect_reason_id,
                    reported_by, is_confirmed, source_system, source_record_id,
                    entered_by_user_id, comment
                ) VALUES (
                    :run_id, :event_at, :quantity, :reason_id,
                    'OPERATOR', false, 'WEB', :source_id, :user_id, :comment
                )
                ON CONFLICT (source_system, source_record_id)
                WHERE source_record_id IS NOT NULL
                DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    defect_reason_id = EXCLUDED.defect_reason_id,
                    occurred_at = EXCLUDED.occurred_at,
                    comment = EXCLUDED.comment
                RETURNING id
            """),
            {
                "run_id": run_id,
                "event_at": event_at,
                "quantity": quantity,
                "reason_id": reason_id,
                "source_id": f"WEB:{client_event_id}",
                "user_id": UUID(user["id"]),
                "comment": comment,
            },
        ).scalar_one()

    return {"status": "ok", "event_id": str(event_id), "occurred_at": event_at.isoformat()}


def _report_decimal(report: dict, key: str) -> Decimal | None:
    value = (report or {}).get(key)
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).replace(",", "."))
    except Exception:
        return None
    return number if number >= 0 else None


def save_shift_assignment_report(user, run_id, report: dict) -> dict:
    with engine.begin() as connection:
        run = _load_run(connection, run_id)
        user_id = UUID(user["id"])
        report_json = json.dumps(report or {}, ensure_ascii=False, default=str)

        connection.execute(
            text("""
                UPDATE production_runs
                SET shift_assignment_report = CAST(:report AS jsonb),
                    shift_assignment_report_updated_at = now(),
                    shift_assignment_report_updated_by = :user_id,
                    updated_at = now()
                WHERE id = :run_id
            """),
            {
                "run_id": run_id,
                "report": report_json,
                "user_id": user_id,
            },
        )

        # The shift assignment is the operator's final summary for the run.
        # Store the final output as a FINAL event so dashboards/OEE use it
        # without accumulating duplicate quantities on repeated saves.
        event_at = run["shift_ended_at"] - timedelta(seconds=1)
        output_qty = _report_decimal(report, "actual_qty")
        defect_qty = _report_decimal(report, "defect_qty")

        if output_qty is not None:
            connection.execute(
                text("""
                    INSERT INTO production_output_events (
                        production_run_id,
                        occurred_at,
                        quantity,
                        event_kind,
                        status,
                        source_system,
                        source_record_id,
                        entered_by_user_id,
                        comment
                    ) VALUES (
                        :run_id,
                        :event_at,
                        :quantity,
                        'FINAL',
                        'RECORDED',
                        'WEB',
                        :source_id,
                        :user_id,
                        'Итоговый выпуск из сменного задания'
                    )
                    ON CONFLICT (source_system, source_record_id)
                    WHERE source_record_id IS NOT NULL
                    DO UPDATE SET
                        occurred_at = EXCLUDED.occurred_at,
                        quantity = EXCLUDED.quantity,
                        event_kind = 'FINAL',
                        status = 'RECORDED',
                        entered_by_user_id = EXCLUDED.entered_by_user_id,
                        comment = EXCLUDED.comment
                """),
                {
                    "run_id": run_id,
                    "event_at": event_at,
                    "quantity": output_qty,
                    "source_id": f"SHIFT_ASSIGNMENT:{run_id}:OUTPUT",
                    "user_id": user_id,
                },
            )

            if output_qty > 0:
                connection.execute(
                    text("""
                        UPDATE production_runs
                        SET status = CASE
                                WHEN status IN ('COMPLETED','VERIFIED') THEN status
                                ELSE 'RUNNING'
                            END,
                            updated_at = now()
                        WHERE id = :run_id
                    """),
                    {"run_id": run_id},
                )

        defect_source_id = f"SHIFT_ASSIGNMENT:{run_id}:DEFECT"
        if defect_qty is not None and defect_qty > 0:
            connection.execute(
                text("""
                    INSERT INTO defect_events (
                        production_run_id,
                        occurred_at,
                        quantity,
                        defect_reason_id,
                        reported_by,
                        is_confirmed,
                        source_system,
                        source_record_id,
                        entered_by_user_id,
                        comment
                    ) VALUES (
                        :run_id,
                        :event_at,
                        :quantity,
                        NULL,
                        'OPERATOR',
                        false,
                        'WEB',
                        :source_id,
                        :user_id,
                        'Итоговый брак из сменного задания'
                    )
                    ON CONFLICT (source_system, source_record_id)
                    WHERE source_record_id IS NOT NULL
                    DO UPDATE SET
                        occurred_at = EXCLUDED.occurred_at,
                        quantity = EXCLUDED.quantity,
                        entered_by_user_id = EXCLUDED.entered_by_user_id,
                        comment = EXCLUDED.comment
                """),
                {
                    "run_id": run_id,
                    "event_at": event_at,
                    "quantity": defect_qty,
                    "source_id": defect_source_id,
                    "user_id": user_id,
                },
            )
        elif defect_qty == 0:
            connection.execute(
                text("""
                    DELETE FROM defect_events
                    WHERE source_system = 'WEB'
                      AND source_record_id = :source_id
                """),
                {"source_id": defect_source_id},
            )

        connection.execute(
            text("""
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
                    CAST(:report AS jsonb),
                    'Сохранение интерактивного сменного задания оператора'
                )
            """),
            {
                "run_id": run_id,
                "user_id": user_id,
                "report": report_json,
            },
        )

    return {
        "status": "ok",
        "production_run_id": str(run["id"]),
        "report": report or {},
        "facts_synced": {
            "output_qty": float(output_qty) if output_qty is not None else None,
            "operator_defect_qty": float(defect_qty) if defect_qty is not None else None,
        },
    }
