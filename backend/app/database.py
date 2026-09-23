import json

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings


engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)


def stage_external_events(events: list[dict]) -> dict:
    if not events:
        return {"received": 0, "inserted_or_updated": 0}

    statement = text(
        """
        INSERT INTO external_event_staging (
            source_system,
            event_type,
            source_document_id,
            source_sheet,
            source_row,
            source_record_key,
            response_at,
            business_date,
            shift_code,
            occurred_at,
            ended_at,
            personnel_number,
            equipment_code,
            order_no,
            article_code,
            ticket_no,
            quantity,
            secondary_quantity,
            good_quantity,
            payload,
            processing_status,
            resolution_status,
            updated_at
        ) VALUES (
            :source_system,
            :event_type,
            :source_document_id,
            :source_sheet,
            :source_row,
            :source_record_key,
            :response_at,
            :business_date,
            :shift_code,
            :occurred_at,
            :ended_at,
            :personnel_number,
            :equipment_code,
            :order_no,
            :article_code,
            :ticket_no,
            :quantity,
            :secondary_quantity,
            :good_quantity,
            CAST(:payload AS jsonb),
            'PENDING',
            'UNRESOLVED',
            now()
        )
        ON CONFLICT (source_record_key)
        DO UPDATE SET
            response_at = EXCLUDED.response_at,
            business_date = EXCLUDED.business_date,
            shift_code = EXCLUDED.shift_code,
            occurred_at = EXCLUDED.occurred_at,
            ended_at = EXCLUDED.ended_at,
            personnel_number = EXCLUDED.personnel_number,
            equipment_code = EXCLUDED.equipment_code,
            order_no = EXCLUDED.order_no,
            article_code = EXCLUDED.article_code,
            ticket_no = EXCLUDED.ticket_no,
            quantity = EXCLUDED.quantity,
            secondary_quantity = EXCLUDED.secondary_quantity,
            good_quantity = EXCLUDED.good_quantity,
            payload = EXCLUDED.payload,
            processing_status = CASE
                WHEN external_event_staging.payload IS DISTINCT FROM EXCLUDED.payload THEN 'PENDING'
                ELSE external_event_staging.processing_status
            END,
            resolution_status = CASE
                WHEN external_event_staging.payload IS DISTINCT FROM EXCLUDED.payload THEN 'UNRESOLVED'
                ELSE external_event_staging.resolution_status
            END,
            error_message = NULL,
            updated_at = now()
        """
    )

    rows = []
    for event in events:
        item = dict(event)
        item["payload"] = json.dumps(item["payload"], ensure_ascii=False, default=str)
        rows.append(item)

    with engine.begin() as connection:
        connection.execute(statement, rows)

    return {"received": len(events), "inserted_or_updated": len(events)}


def latest_staged_events(event_type: str, limit: int = 100) -> list[dict]:
    statement = text(
        """
        SELECT *
        FROM external_event_staging
        WHERE event_type = :event_type
        ORDER BY occurred_at DESC NULLS LAST, source_row DESC
        LIMIT :limit
        """
    )
    with engine.begin() as connection:
        return [
            dict(row)
            for row in connection.execute(
                statement,
                {"event_type": event_type, "limit": limit},
            ).mappings()
        ]
