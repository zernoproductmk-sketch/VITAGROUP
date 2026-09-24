from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from .database import engine


def list_reasons() -> dict:
    with engine.begin() as connection:
        downtime = connection.execute(
            text(
                """
                SELECT
                    id,
                    code,
                    category,
                    name,
                    affects_availability,
                    is_planned,
                    is_active
                FROM downtime_reasons
                ORDER BY is_active DESC, category, name
                """
            )
        ).mappings().all()

        defects = connection.execute(
            text(
                """
                SELECT
                    id,
                    code,
                    category,
                    name,
                    is_active
                FROM defect_reasons
                ORDER BY is_active DESC, category NULLS LAST, name
                """
            )
        ).mappings().all()

    return {
        "downtime": [
            {**dict(row), "id": str(row["id"])}
            for row in downtime
        ],
        "defects": [
            {**dict(row), "id": str(row["id"])}
            for row in defects
        ],
    }


def upsert_downtime_reason(
    *,
    reason_id: UUID | None,
    code: str,
    category: str,
    name: str,
    affects_availability: bool,
    is_planned: bool,
    is_active: bool,
) -> dict:
    code = code.strip().upper()
    category = category.strip()
    name = name.strip()

    if not code or not category or not name:
        raise ValueError("Код, категория и наименование обязательны")

    with engine.begin() as connection:
        if reason_id:
            row = connection.execute(
                text(
                    """
                    UPDATE downtime_reasons
                    SET code = :code,
                        category = :category,
                        name = :name,
                        affects_availability = :affects_availability,
                        is_planned = :is_planned,
                        is_active = :is_active
                    WHERE id = :id
                    RETURNING *
                    """
                ),
                {
                    "id": reason_id,
                    "code": code,
                    "category": category,
                    "name": name,
                    "affects_availability": affects_availability,
                    "is_planned": is_planned,
                    "is_active": is_active,
                },
            ).mappings().first()
            if not row:
                raise LookupError("Причина простоя не найдена")
        else:
            row = connection.execute(
                text(
                    """
                    INSERT INTO downtime_reasons (
                        code,
                        category,
                        name,
                        affects_availability,
                        is_planned,
                        is_active
                    ) VALUES (
                        :code,
                        :category,
                        :name,
                        :affects_availability,
                        :is_planned,
                        :is_active
                    )
                    ON CONFLICT (code)
                    DO UPDATE SET
                        category = EXCLUDED.category,
                        name = EXCLUDED.name,
                        affects_availability = EXCLUDED.affects_availability,
                        is_planned = EXCLUDED.is_planned,
                        is_active = EXCLUDED.is_active
                    RETURNING *
                    """
                ),
                {
                    "code": code,
                    "category": category,
                    "name": name,
                    "affects_availability": affects_availability,
                    "is_planned": is_planned,
                    "is_active": is_active,
                },
            ).mappings().one()

    return {**dict(row), "id": str(row["id"])}


def upsert_defect_reason(
    *,
    reason_id: UUID | None,
    code: str,
    category: str | None,
    name: str,
    is_active: bool,
) -> dict:
    code = code.strip().upper()
    category = (category or "").strip() or None
    name = name.strip()

    if not code or not name:
        raise ValueError("Код и наименование обязательны")

    with engine.begin() as connection:
        if reason_id:
            row = connection.execute(
                text(
                    """
                    UPDATE defect_reasons
                    SET code = :code,
                        category = :category,
                        name = :name,
                        is_active = :is_active
                    WHERE id = :id
                    RETURNING *
                    """
                ),
                {
                    "id": reason_id,
                    "code": code,
                    "category": category,
                    "name": name,
                    "is_active": is_active,
                },
            ).mappings().first()
            if not row:
                raise LookupError("Причина брака не найдена")
        else:
            row = connection.execute(
                text(
                    """
                    INSERT INTO defect_reasons (
                        code,
                        category,
                        name,
                        is_active
                    ) VALUES (
                        :code,
                        :category,
                        :name,
                        :is_active
                    )
                    ON CONFLICT (code)
                    DO UPDATE SET
                        category = EXCLUDED.category,
                        name = EXCLUDED.name,
                        is_active = EXCLUDED.is_active
                    RETURNING *
                    """
                ),
                {
                    "code": code,
                    "category": category,
                    "name": name,
                    "is_active": is_active,
                },
            ).mappings().one()

    return {**dict(row), "id": str(row["id"])}
