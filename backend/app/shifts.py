from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings


def ensure_shift(connection, business_date, shift_code):
    if not business_date or not shift_code:
        return None

    existing = connection.execute(
        text(
            """
            SELECT s.id
            FROM shifts s
            JOIN shift_types st ON st.id = s.shift_type_id
            WHERE s.business_date = :business_date
              AND st.code = :shift_code
            LIMIT 1
            """
        ),
        {"business_date": business_date, "shift_code": shift_code},
    ).scalar_one_or_none()
    if existing:
        return existing

    shift_type = connection.execute(
        text(
            """
            SELECT id, start_time, end_time, crosses_midnight
            FROM shift_types
            WHERE code = :shift_code
            """
        ),
        {"shift_code": shift_code},
    ).mappings().first()
    if not shift_type:
        return None

    tz = ZoneInfo(settings.business_timezone)
    started_at = datetime.combine(
        business_date,
        shift_type["start_time"],
        tzinfo=tz,
    )
    end_date = business_date + timedelta(days=1) if shift_type["crosses_midnight"] else business_date
    ended_at = datetime.combine(
        end_date,
        shift_type["end_time"],
        tzinfo=tz,
    )

    connection.execute(
        text(
            """
            INSERT INTO shifts (
                shift_type_id,
                business_date,
                started_at,
                ended_at,
                status
            ) VALUES (
                :shift_type_id,
                :business_date,
                :started_at,
                :ended_at,
                'OPEN'
            )
            ON CONFLICT (shift_type_id, business_date) DO NOTHING
            """
        ),
        {
            "shift_type_id": shift_type["id"],
            "business_date": business_date,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )

    return connection.execute(
        text(
            """
            SELECT s.id
            FROM shifts s
            JOIN shift_types st ON st.id = s.shift_type_id
            WHERE s.business_date = :business_date
              AND st.code = :shift_code
            LIMIT 1
            """
        ),
        {"business_date": business_date, "shift_code": shift_code},
    ).scalar_one_or_none()
