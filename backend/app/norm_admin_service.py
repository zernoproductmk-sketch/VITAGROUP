from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from .database import engine


def norm_admin_data() -> dict:
    with engine.begin() as connection:
        products = connection.execute(
            text(
                """
                SELECT id, code, article, name
                FROM products
                WHERE is_active = true
                ORDER BY COALESCE(article, code), name
                """
            )
        ).mappings().all()

        equipment = connection.execute(
            text(
                """
                SELECT id, code, name
                FROM equipment
                WHERE is_active = true
                ORDER BY code
                """
            )
        ).mappings().all()

        norms = connection.execute(
            text(
                """
                SELECT
                    n.id,
                    n.product_id,
                    n.equipment_id,
                    n.ideal_rate_per_hour,
                    n.valid_from,
                    n.valid_to,
                    n.source_system,
                    n.source_record_id,
                    p.code AS product_code,
                    p.article AS product_article,
                    p.name AS product_name,
                    e.code AS equipment_code,
                    e.name AS equipment_name
                FROM production_norms n
                JOIN products p ON p.id = n.product_id
                JOIN equipment e ON e.id = n.equipment_id
                ORDER BY
                    n.valid_from DESC,
                    e.code,
                    COALESCE(p.article, p.code)
                """
            )
        ).mappings().all()

    def serialize(row):
        result = dict(row)
        for key in ("id", "product_id", "equipment_id"):
            if result.get(key):
                result[key] = str(result[key])
        if result.get("ideal_rate_per_hour") is not None:
            result["ideal_rate_per_hour"] = float(
                result["ideal_rate_per_hour"]
            )
        if result.get("valid_from"):
            result["valid_from"] = result["valid_from"].isoformat()
        if result.get("valid_to"):
            result["valid_to"] = result["valid_to"].isoformat()
        return result

    return {
        "products": [
            {
                **dict(row),
                "id": str(row["id"]),
            }
            for row in products
        ],
        "equipment": [
            {
                **dict(row),
                "id": str(row["id"]),
            }
            for row in equipment
        ],
        "norms": [serialize(row) for row in norms],
    }


def _assert_no_overlap(
    connection,
    *,
    norm_id: UUID | None,
    product_id: UUID,
    equipment_id: UUID,
    valid_from: date,
    valid_to: date | None,
) -> None:
    overlap = connection.execute(
        text(
            """
            SELECT
                n.id,
                n.valid_from,
                n.valid_to,
                n.source_system
            FROM production_norms n
            WHERE n.product_id = :product_id
              AND n.equipment_id = :equipment_id
              AND n.operation_id IS NULL
              AND (
                    CAST(:norm_id AS uuid) IS NULL
                    OR n.id <> CAST(:norm_id AS uuid)
                  )
              AND daterange(
                    n.valid_from,
                    COALESCE(n.valid_to + 1, 'infinity'::date),
                    '[)'
                  )
                  &&
                  daterange(
                    CAST(:valid_from AS date),
                    COALESCE(CAST(:valid_to AS date) + 1, 'infinity'::date),
                    '[)'
                  )
            ORDER BY n.valid_from
            LIMIT 1
            """
        ),
        {
            "norm_id": norm_id,
            "product_id": product_id,
            "equipment_id": equipment_id,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    ).mappings().first()

    if overlap:
        end = overlap["valid_to"].isoformat() if overlap["valid_to"] else "без окончания"
        raise ValueError(
            "Период пересекается с существующим нормативом "
            f"{overlap['valid_from'].isoformat()} — {end} "
            f"({overlap['source_system']})"
        )


def save_manual_norm(
    *,
    norm_id: UUID | None,
    product_id: UUID,
    equipment_id: UUID,
    ideal_rate_per_hour: Decimal,
    valid_from: date,
    valid_to: date | None,
    apply_to_open_runs: bool,
    user_id: UUID,
) -> dict:
    if ideal_rate_per_hour <= 0:
        raise ValueError("Норма должна быть больше нуля")
    if valid_to and valid_to < valid_from:
        raise ValueError("Дата окончания не может быть раньше даты начала")

    with engine.begin() as connection:
        product_exists = connection.execute(
            text("SELECT 1 FROM products WHERE id=:id AND is_active=true"),
            {"id": product_id},
        ).scalar_one_or_none()
        equipment_exists = connection.execute(
            text("SELECT 1 FROM equipment WHERE id=:id AND is_active=true"),
            {"id": equipment_id},
        ).scalar_one_or_none()

        if not product_exists:
            raise LookupError("Номенклатура не найдена или неактивна")
        if not equipment_exists:
            raise LookupError("Линия не найдена или неактивна")

        _assert_no_overlap(
            connection,
            norm_id=norm_id,
            product_id=product_id,
            equipment_id=equipment_id,
            valid_from=valid_from,
            valid_to=valid_to,
        )

        if norm_id:
            existing = connection.execute(
                text(
                    """
                    SELECT *
                    FROM production_norms
                    WHERE id=:id
                    FOR UPDATE
                    """
                ),
                {"id": norm_id},
            ).mappings().first()
            if not existing:
                raise LookupError("Норматив не найден")
            if existing["source_system"] != "WEB":
                raise ValueError(
                    "Внешний норматив нельзя редактировать вручную. "
                    "Создайте отдельный резервный норматив после завершения "
                    "его периода действия."
                )

            connection.execute(
                text(
                    """
                    UPDATE production_norms
                    SET product_id=:product_id,
                        equipment_id=:equipment_id,
                        ideal_rate_per_hour=:rate,
                        valid_from=:valid_from,
                        valid_to=:valid_to,
                        source_system='WEB',
                        source_record_id=COALESCE(
                            source_record_id,
                            'MANUAL:' || id::text
                        )
                    WHERE id=:id
                    """
                ),
                {
                    "id": norm_id,
                    "product_id": product_id,
                    "equipment_id": equipment_id,
                    "rate": ideal_rate_per_hour,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
            )
            saved_id = norm_id
            audit_action = "UPDATE"
        else:
            saved_id = connection.execute(
                text(
                    """
                    INSERT INTO production_norms (
                        product_id,
                        equipment_id,
                        operation_id,
                        ideal_rate_per_hour,
                        valid_from,
                        valid_to,
                        source_system,
                        source_record_id
                    ) VALUES (
                        :product_id,
                        :equipment_id,
                        NULL,
                        :rate,
                        :valid_from,
                        :valid_to,
                        'WEB',
                        NULL
                    )
                    RETURNING id
                    """
                ),
                {
                    "product_id": product_id,
                    "equipment_id": equipment_id,
                    "rate": ideal_rate_per_hour,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    UPDATE production_norms
                    SET source_record_id='MANUAL:' || id::text
                    WHERE id=:id
                    """
                ),
                {"id": saved_id},
            )
            audit_action = "INSERT"

        applied_runs = 0
        if apply_to_open_runs:
            applied_runs = connection.execute(
                text(
                    """
                    UPDATE production_runs pr
                    SET ideal_rate_per_hour=:rate,
                        updated_at=now()
                    FROM shifts s
                    WHERE pr.shift_id=s.id
                      AND pr.product_id=:product_id
                      AND pr.equipment_id=:equipment_id
                      AND pr.ideal_rate_per_hour IS NULL
                      AND pr.status IN ('PLANNED','RUNNING','PAUSED')
                      AND s.business_date >= :valid_from
                      AND (
                            CAST(:valid_to AS date) IS NULL
                            OR s.business_date <= CAST(:valid_to AS date)
                          )
                    """
                ),
                {
                    "rate": ideal_rate_per_hour,
                    "product_id": product_id,
                    "equipment_id": equipment_id,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
            ).rowcount

        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    table_name,
                    record_id,
                    action,
                    changed_by_user_id,
                    new_data,
                    reason
                ) VALUES (
                    'production_norms',
                    :record_id,
                    :action,
                    :user_id,
                    jsonb_build_object(
                        'product_id', CAST(:product_id AS text),
                        'equipment_id', CAST(:equipment_id AS text),
                        'ideal_rate_per_hour', CAST(:rate AS text),
                        'valid_from', CAST(:valid_from AS text),
                        'valid_to', CASE
                            WHEN :valid_to IS NULL THEN NULL
                            ELSE CAST(:valid_to AS text)
                        END,
                        'source_system', 'WEB'
                    ),
                    'Ручной резервный норматив скорости'
                )
                """
            ),
            {
                "record_id": saved_id,
                "action": audit_action,
                "user_id": user_id,
                "product_id": product_id,
                "equipment_id": equipment_id,
                "rate": ideal_rate_per_hour,
                "valid_from": valid_from,
                "valid_to": valid_to,
            },
        )

        row = connection.execute(
            text(
                """
                SELECT
                    n.id,
                    n.product_id,
                    n.equipment_id,
                    n.ideal_rate_per_hour,
                    n.valid_from,
                    n.valid_to,
                    n.source_system,
                    p.article AS product_article,
                    p.code AS product_code,
                    p.name AS product_name,
                    e.code AS equipment_code,
                    e.name AS equipment_name
                FROM production_norms n
                JOIN products p ON p.id=n.product_id
                JOIN equipment e ON e.id=n.equipment_id
                WHERE n.id=:id
                """
            ),
            {"id": saved_id},
        ).mappings().one()

    result = dict(row)
    for key in ("id", "product_id", "equipment_id"):
        result[key] = str(result[key])
    result["ideal_rate_per_hour"] = float(result["ideal_rate_per_hour"])
    result["valid_from"] = result["valid_from"].isoformat()
    result["valid_to"] = (
        result["valid_to"].isoformat()
        if result["valid_to"]
        else None
    )
    result["applied_runs"] = applied_runs
    return result
