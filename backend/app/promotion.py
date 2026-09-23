from __future__ import annotations

from sqlalchemy import text

from .database import engine


def _ensure_shift_id(connection, event: dict):
    return event.get("shift_id")


def promote_resolved_events(limit: int = 500) -> dict:
    counters = {"processed": 0, "promoted": 0, "skipped": 0, "errors": 0}

    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM external_event_staging
                WHERE resolution_status = 'RESOLVED'
                  AND processing_status = 'PENDING'
                ORDER BY response_at, source_row
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": limit},
        ).mappings().all()

        for raw in rows:
            event = dict(raw)
            counters["processed"] += 1
            try:
                kind = event["event_type"]
                source_record_id = event["source_record_key"]

                if kind == "production_output":
                    connection.execute(
                        text(
                            """
                            INSERT INTO production_output_events (
                                production_run_id, occurred_at, quantity, event_kind,
                                status, source_system, source_record_id, comment
                            ) VALUES (
                                :run_id, :occurred_at, :quantity, 'INCREMENT',
                                'RECORDED', 'COVERSE', :source_record_id, :comment
                            )
                            ON CONFLICT (source_system, source_record_id) DO UPDATE SET
                                production_run_id = EXCLUDED.production_run_id,
                                occurred_at = EXCLUDED.occurred_at,
                                quantity = EXCLUDED.quantity,
                                comment = EXCLUDED.comment
                            """
                        ),
                        {
                            "run_id": event["production_run_id"],
                            "occurred_at": event["occurred_at"],
                            "quantity": event["quantity"] or event["good_quantity"] or 0,
                            "source_record_id": source_record_id,
                            "comment": "Импорт Coverse: счетчик/выпуск производства",
                        },
                    )
                    if event.get("secondary_quantity") is not None:
                        defect_source_id = f"{source_record_id}|OPERATOR_DEFECT"
                        connection.execute(
                            text(
                                """
                                INSERT INTO defect_events (
                                    production_run_id, occurred_at, quantity,
                                    reported_by, is_confirmed, source_system,
                                    source_record_id, comment
                                ) VALUES (
                                    :run_id, :occurred_at, :quantity,
                                    'OPERATOR', false, 'COVERSE',
                                    :source_record_id, :comment
                                )
                                ON CONFLICT (source_system, source_record_id) DO UPDATE SET
                                    production_run_id = EXCLUDED.production_run_id,
                                    occurred_at = EXCLUDED.occurred_at,
                                    quantity = EXCLUDED.quantity
                                """
                            ),
                            {
                                "run_id": event["production_run_id"],
                                "occurred_at": event["occurred_at"],
                                "quantity": event["secondary_quantity"],
                                "source_record_id": defect_source_id,
                                "comment": "Брак по форме оператора",
                            },
                        )

                elif kind == "qc_defects":
                    connection.execute(
                        text(
                            """
                            INSERT INTO defect_events (
                                production_run_id, occurred_at, quantity,
                                reported_by, is_confirmed, source_system,
                                source_record_id, comment
                            ) VALUES (
                                :run_id, :occurred_at, :quantity,
                                'QC', true, 'COVERSE',
                                :source_record_id, :comment
                            )
                            ON CONFLICT (source_system, source_record_id) DO UPDATE SET
                                production_run_id = EXCLUDED.production_run_id,
                                occurred_at = EXCLUDED.occurred_at,
                                quantity = EXCLUDED.quantity,
                                is_confirmed = true
                            """
                        ),
                        {
                            "run_id": event["production_run_id"],
                            "occurred_at": event["occurred_at"],
                            "quantity": event["quantity"] or 0,
                            "source_record_id": source_record_id,
                            "comment": "Подтвержденный брак ОТК",
                        },
                    )

                elif kind == "downtime":
                    connection.execute(
                        text(
                            """
                            INSERT INTO downtime_events (
                                production_run_id, equipment_id, shift_id,
                                started_at, ended_at, is_planned,
                                source_system, source_record_id, comment
                            ) VALUES (
                                :run_id, :equipment_id, :shift_id,
                                :started_at, :ended_at, false,
                                'COVERSE', :source_record_id, :comment
                            )
                            ON CONFLICT (source_system, source_record_id) DO UPDATE SET
                                production_run_id = EXCLUDED.production_run_id,
                                equipment_id = EXCLUDED.equipment_id,
                                shift_id = EXCLUDED.shift_id,
                                started_at = EXCLUDED.started_at,
                                ended_at = EXCLUDED.ended_at,
                                comment = EXCLUDED.comment
                            """
                        ),
                        {
                            "run_id": event.get("production_run_id"),
                            "equipment_id": event["equipment_id"],
                            "shift_id": event["shift_id"],
                            "started_at": event["occurred_at"],
                            "ended_at": event.get("ended_at"),
                            "source_record_id": source_record_id,
                            "comment": str(event.get("payload", {}).get("reason") or "Простой Coverse"),
                        },
                    )

                elif kind == "warehouse":
                    connection.execute(
                        text(
                            """
                            INSERT INTO warehouse_receipts (
                                production_run_id, shift_id, product_id,
                                received_at, quantity, warehouse_document_no,
                                source_system, source_record_id
                            ) VALUES (
                                :run_id, :shift_id, :product_id,
                                :received_at, :quantity, :document_no,
                                'COVERSE', :source_record_id
                            )
                            ON CONFLICT (source_system, source_record_id) DO UPDATE SET
                                production_run_id = EXCLUDED.production_run_id,
                                shift_id = EXCLUDED.shift_id,
                                product_id = EXCLUDED.product_id,
                                received_at = EXCLUDED.received_at,
                                quantity = EXCLUDED.quantity,
                                warehouse_document_no = EXCLUDED.warehouse_document_no
                            """
                        ),
                        {
                            "run_id": event.get("production_run_id"),
                            "shift_id": event["shift_id"],
                            "product_id": event["product_id"],
                            "received_at": event["occurred_at"],
                            "quantity": event["quantity"] or 0,
                            "document_no": event.get("ticket_no"),
                            "source_record_id": source_record_id,
                        },
                    )

                elif kind == "accountant":
                    # Accountant rows are a control layer. They remain available
                    # in staging and are linked by ticket to warehouse events.
                    counters["skipped"] += 1
                    connection.execute(
                        text(
                            """
                            UPDATE external_event_staging
                            SET processing_status = 'RESOLVED', updated_at = now()
                            WHERE id = :id
                            """
                        ),
                        {"id": event["id"]},
                    )
                    continue

                else:
                    counters["skipped"] += 1
                    continue

                connection.execute(
                    text(
                        """
                        UPDATE external_event_staging
                        SET processing_status = 'RESOLVED',
                            error_message = NULL,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {"id": event["id"]},
                )
                counters["promoted"] += 1

            except Exception as exc:
                counters["errors"] += 1
                connection.execute(
                    text(
                        """
                        UPDATE external_event_staging
                        SET processing_status = 'ERROR',
                            error_message = :message,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {"id": event["id"], "message": str(exc)[:2000]},
                )

    return counters
