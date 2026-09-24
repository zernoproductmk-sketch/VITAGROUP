from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from .database import engine
from .integrations.coverse import CoverseClient
from .normalization import normalized_code, normalized_personnel_number, parse_decimal
from .reference_sources import REFERENCE_SOURCES, parse_reference_rows, validate_headers


def _excel_serial_to_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    try:
        serial = Decimal(text_value.replace(",", "."))
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except Exception:
        pass
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            pass
    return None


def _is_active_text(value) -> bool:
    text_value = str(value or "").strip().lower()
    return text_value not in {"не действует", "недействующий", "архив", "закрыт", "inactive", "0", "нет"}


def _start_log(connection, source) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO master_data_sync_log (
                source_system, source_key, source_document_id, source_sheet
            ) VALUES ('COVERSE', :key, :document_id, :sheet)
            RETURNING id
            """
        ),
        {"key": source.key, "document_id": source.document_id, "sheet": source.sheet_name},
    ).scalar_one()


def _finish_log(connection, log_id: int, *, status: str, rows_read: int, rows_applied: int, rows_skipped: int, rows_error: int, message: str | None = None, details: dict | None = None):
    connection.execute(
        text(
            """
            UPDATE master_data_sync_log
            SET completed_at = now(),
                status = :status,
                rows_read = :rows_read,
                rows_applied = :rows_applied,
                rows_skipped = :rows_skipped,
                rows_error = :rows_error,
                message = :message,
                details = CAST(:details AS jsonb)
            WHERE id = :id
            """
        ),
        {
            "id": log_id,
            "status": status,
            "rows_read": rows_read,
            "rows_applied": rows_applied,
            "rows_skipped": rows_skipped,
            "rows_error": rows_error,
            "message": message,
            "details": json.dumps(details or {}, ensure_ascii=False, default=str),
        },
    )


def _resolve_previous_issues(connection, source) -> int:
    result = connection.execute(
        text(
            """
            UPDATE master_data_sync_issues
            SET status = 'RESOLVED',
                resolved_at = now()
            WHERE source_system = 'COVERSE'
              AND source_key = :key
              AND source_document_id = :document_id
              AND source_sheet = :sheet
              AND status = 'OPEN'
            """
        ),
        {
            "key": source.key,
            "document_id": source.document_id,
            "sheet": source.sheet_name,
        },
    )
    return int(result.rowcount or 0)


def _issue(connection, source, row_number, code, message, raw_data=None, severity="ERROR"):
    connection.execute(
        text(
            """
            INSERT INTO master_data_sync_issues (
                source_system, source_key, source_document_id, source_sheet,
                source_row, issue_code, severity, message, raw_data
            ) VALUES (
                'COVERSE', :key, :document_id, :sheet,
                :row_number, :code, :severity, :message, CAST(:raw_data AS jsonb)
            )
            """
        ),
        {
            "key": source.key,
            "document_id": source.document_id,
            "sheet": source.sheet_name,
            "row_number": row_number,
            "code": code,
            "severity": severity,
            "message": message,
            "raw_data": json.dumps(raw_data, ensure_ascii=False, default=str) if raw_data is not None else None,
        },
    )


def _upsert_employee(connection, row):
    personnel_number = normalized_personnel_number(row.get("personnel_number"))
    full_name = str(row.get("full_name") or "").strip()
    if not personnel_number or not full_name:
        raise ValueError("Нет табельного номера или ФИО")

    connection.execute(
        text(
            """
            INSERT INTO employees (
                personnel_number, full_name, position_name, department_name, is_active
            ) VALUES (
                :personnel_number, :full_name, :position_name, :department_name, true
            )
            ON CONFLICT (personnel_number) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                position_name = EXCLUDED.position_name,
                department_name = EXCLUDED.department_name,
                is_active = true,
                updated_at = now()
            """
        ),
        {
            "personnel_number": personnel_number,
            "full_name": full_name,
            "position_name": row.get("position_name"),
            "department_name": row.get("department_name"),
        },
    )


def _upsert_equipment(connection, row):
    canonical = normalized_code(row.get("canonical_form_name") or row.get("name"))
    name = str(row.get("name") or canonical or "").strip()
    if not canonical:
        raise ValueError("Нет кода линии")

    equipment_id = connection.execute(
        text(
            """
            INSERT INTO equipment (code, name, is_active)
            VALUES (:code, :name, :is_active)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            RETURNING id
            """
        ),
        {"code": canonical, "name": name, "is_active": _is_active_text(row.get("status"))},
    ).scalar_one()

    aliases = {
        row.get("name"),
        row.get("canonical_form_name"),
        row.get("norm_name"),
        row.get("tariff_name"),
    }
    for alias in {normalized_code(item) for item in aliases if item}:
        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system, entity_type, external_code, entity_id, canonical_label
                ) VALUES ('COVERSE', 'EQUIPMENT', :external_code, :entity_id, :label)
                ON CONFLICT (source_system, entity_type, external_code)
                DO UPDATE SET entity_id = EXCLUDED.entity_id,
                              canonical_label = EXCLUDED.canonical_label,
                              is_active = true,
                              updated_at = now()
                """
            ),
            {"external_code": alias, "entity_id": equipment_id, "label": canonical},
        )


def _upsert_product(connection, row):
    article = str(row.get("article") or "").strip()
    warehouse_code = normalized_code(row.get("warehouse_code"))
    name = str(row.get("name") or "").strip()
    if not article or not warehouse_code or not name:
        raise ValueError("Нет артикула, складского кода или наименования")

    product_id = connection.execute(
        text(
            """
            INSERT INTO products (code, article, name, unit, is_active)
            VALUES (:code, :article, :name, 'pcs', :is_active)
            ON CONFLICT (code) DO UPDATE SET
                article = EXCLUDED.article,
                name = EXCLUDED.name,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "code": article,
            "article": article,
            "name": name,
            "is_active": _is_active_text(row.get("status")),
        },
    ).scalar_one()

    for code_type, external_code in (
        ("WAREHOUSE_CODE", warehouse_code),
        ("ARTICLE", article),
        ("COMBINED_ARTICLE", row.get("combined_article")),
    ):
        if not external_code:
            continue
        code = normalized_code(external_code)
        connection.execute(
            text(
                """
                INSERT INTO product_external_codes (
                    product_id, source_system, code_type, external_code, is_primary, metadata
                ) VALUES (
                    :product_id, 'COVERSE', :code_type, :external_code,
                    :is_primary, CAST(:metadata AS jsonb)
                )
                ON CONFLICT (source_system, code_type, external_code)
                DO UPDATE SET product_id = EXCLUDED.product_id,
                              is_active = true,
                              updated_at = now()
                """
            ),
            {
                "product_id": product_id,
                "code_type": code_type,
                "external_code": code,
                "is_primary": code_type == "WAREHOUSE_CODE",
                "metadata": json.dumps({"product_kind": row.get("product_kind")}, ensure_ascii=False),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO external_reference_aliases (
                    source_system, entity_type, external_code, entity_id, canonical_label
                ) VALUES ('COVERSE', 'PRODUCT', :external_code, :entity_id, :label)
                ON CONFLICT (source_system, entity_type, external_code)
                DO UPDATE SET entity_id = EXCLUDED.entity_id,
                              canonical_label = EXCLUDED.canonical_label,
                              is_active = true,
                              updated_at = now()
                """
            ),
            {"external_code": code, "entity_id": product_id, "label": article},
        )


def _upsert_tariff(connection, row):
    equipment_code = normalized_code(row.get("equipment_code"))
    rate = parse_decimal(row.get("rate"))
    valid_from = _excel_serial_to_date(row.get("valid_from"))
    unit = str(row.get("unit") or "").strip()
    accrual_type = str(row.get("accrual_type") or "").strip()
    if not accrual_type or not unit or rate is None or valid_from is None:
        raise ValueError("Неполные ключевые поля тарифа")

    equipment_id = None
    if equipment_code:
        equipment_id = connection.execute(
            text(
                """
                SELECT id FROM equipment WHERE upper(code)=upper(:code)
                UNION ALL
                SELECT entity_id FROM external_reference_aliases
                 WHERE source_system='COVERSE'
                   AND entity_type='EQUIPMENT'
                   AND upper(external_code)=upper(:code)
                   AND is_active=true
                LIMIT 1
                """
            ),
            {"code": equipment_code},
        ).scalar_one_or_none()

    source_record_key = "|".join(
        [
            "COVERSE",
            "TARIFF",
            str(row.get("source_document_id")),
            str(row.get("source_sheet")),
            str(row.get("source_row")),
        ]
    )

    connection.execute(
        text(
            """
            INSERT INTO payroll_rate_rules (
                accrual_type, role_name, equipment_id, equipment_external_code,
                product_type, print_flag, tariff_group, unit, rate,
                payment_type, valid_from, source_document_id, source_sheet,
                source_row, source_record_key
            ) VALUES (
                :accrual_type, :role_name, :equipment_id, :equipment_external_code,
                :product_type, :print_flag, :tariff_group, :unit, :rate,
                :payment_type, :valid_from, :source_document_id, :source_sheet,
                :source_row, :source_record_key
            )
            ON CONFLICT (source_record_key) DO UPDATE SET
                accrual_type = EXCLUDED.accrual_type,
                role_name = EXCLUDED.role_name,
                equipment_id = EXCLUDED.equipment_id,
                equipment_external_code = EXCLUDED.equipment_external_code,
                product_type = EXCLUDED.product_type,
                print_flag = EXCLUDED.print_flag,
                tariff_group = EXCLUDED.tariff_group,
                unit = EXCLUDED.unit,
                rate = EXCLUDED.rate,
                payment_type = EXCLUDED.payment_type,
                valid_from = EXCLUDED.valid_from,
                is_active = true,
                updated_at = now()
            """
        ),
        {
            **row,
            "equipment_id": equipment_id,
            "equipment_external_code": equipment_code,
            "rate": rate,
            "valid_from": valid_from,
            "source_record_key": source_record_key,
        },
    )


def _prepare_reference_rows(source_key: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Pre-flight source rows before writes.

    Returns:
        rows_to_apply,
        issues: [{row_number, code, severity, message, raw_data}]
    """
    if source_key == "employees":
        grouped: dict[str, list[dict]] = {}
        passthrough: list[dict] = []

        for row in rows:
            key = normalized_personnel_number(row.get("personnel_number"))
            if not key:
                passthrough.append(row)
                continue
            grouped.setdefault(key, []).append(row)

        prepared = list(passthrough)
        issues: list[dict] = []

        for personnel_number, group in grouped.items():
            if len(group) == 1:
                prepared.append(group[0])
                continue

            fingerprints = {
                (
                    str(item.get("full_name") or "").strip().casefold(),
                    str(item.get("position_name") or "").strip().casefold(),
                    str(item.get("department_name") or "").strip().casefold(),
                )
                for item in group
            }

            if len(fingerprints) == 1:
                prepared.append(group[0])
                for duplicate in group[1:]:
                    issues.append(
                        {
                            "row_number": duplicate.get("source_row"),
                            "code": "DUPLICATE_SOURCE_ROW",
                            "severity": "WARNING",
                            "message": (
                                "Точный дубль сотрудника по табельному номеру; "
                                "строка не загружена повторно"
                            ),
                            "raw_data": {
                                "personnel_number": personnel_number,
                                "source_row": duplicate.get("source_row"),
                            },
                        }
                    )
                continue

            for conflicting in group:
                issues.append(
                    {
                        "row_number": conflicting.get("source_row"),
                        "code": "DUPLICATE_PERSONNEL_CONFLICT",
                        "severity": "ERROR",
                        "message": (
                            "Один табельный номер встречается в нескольких "
                            "различающихся строках. Автоматическая загрузка "
                            "этого сотрудника заблокирована."
                        ),
                        "raw_data": {
                            "personnel_number": personnel_number,
                            "source_row": conflicting.get("source_row"),
                        },
                    }
                )

        prepared.sort(key=lambda item: int(item.get("source_row") or 0))
        return prepared, issues

    if source_key == "products":
        grouped: dict[str, list[dict]] = {}
        passthrough: list[dict] = []

        for row in rows:
            article = str(row.get("article") or "").strip()
            if not article:
                passthrough.append(row)
                continue
            grouped.setdefault(article.casefold(), []).append(row)

        prepared = list(passthrough)
        issues: list[dict] = []

        for article_key, group in grouped.items():
            if len(group) == 1:
                prepared.append(group[0])
                continue

            names = {
                str(item.get("name") or "").strip().casefold()
                for item in group
                if str(item.get("name") or "").strip()
            }

            if len(names) <= 1:
                # One product may legitimately have several warehouse codes.
                prepared.extend(group)
                continue

            for conflicting in group:
                issues.append(
                    {
                        "row_number": conflicting.get("source_row"),
                        "code": "DUPLICATE_ARTICLE_NAME_CONFLICT",
                        "severity": "ERROR",
                        "message": (
                            "Один артикул связан с разными наименованиями. "
                            "Группа заблокирована до ручной проверки; "
                            "складские коды не будут объединены автоматически."
                        ),
                        "raw_data": {
                            "article": str(conflicting.get("article") or "").strip(),
                            "source_row": conflicting.get("source_row"),
                        },
                    }
                )

        prepared.sort(key=lambda item: int(item.get("source_row") or 0))
        return prepared, issues

    return rows, []

HANDLERS = {
    "employees": _upsert_employee,
    "equipment": _upsert_equipment,
    "products": _upsert_product,
    "tariffs": _upsert_tariff,
}


def _preview_row_error(source_key: str, row: dict) -> str | None:
    if source_key == "employees":
        if not normalized_personnel_number(row.get("personnel_number")):
            return "Нет табельного номера"
        if not str(row.get("full_name") or "").strip():
            return "Нет ФИО"
        return None

    if source_key == "equipment":
        canonical = normalized_code(
            row.get("canonical_form_name") or row.get("name")
        )
        if not canonical:
            return "Нет кода линии"
        return None

    if source_key == "products":
        if not str(row.get("name") or "").strip():
            return "Нет наименования"
        if not str(row.get("article") or "").strip():
            return "Нет артикула"
        if not normalized_code(row.get("warehouse_code")):
            return "Нет складского кода"
        return None

    if source_key == "tariffs":
        if not str(row.get("accrual_type") or "").strip():
            return "Нет типа начисления"
        if not str(row.get("unit") or "").strip():
            return "Нет единицы измерения"
        if parse_decimal(row.get("rate")) is None:
            return "Некорректная ставка"
        if _excel_serial_to_date(row.get("valid_from")) is None:
            return "Некорректная дата начала"
        return None

    return None


async def preview_reference(source_key: str) -> dict:
    if source_key not in REFERENCE_SOURCES:
        raise KeyError(source_key)

    source = REFERENCE_SOURCES[source_key]
    client = CoverseClient()
    try:
        cells = await client.read_range(
            source.document_id,
            source.sheet_name,
            source.range_a1,
        )
    finally:
        await client.close()

    header, source_rows = parse_reference_rows(source, cells)
    missing_headers = validate_headers(source, header)

    if missing_headers:
        return {
            "source": source_key,
            "status": "BLOCKED",
            "rows_read": len(source_rows),
            "rows_ready": 0,
            "rows_skipped": len(source_rows),
            "rows_error": 0,
            "missing_headers": missing_headers,
            "issue_counts": {
                "INVALID_SOURCE_SCHEMA": 1,
            },
            "message": (
                "Источник заблокирован: отсутствуют обязательные "
                "заголовки: " + ", ".join(missing_headers)
            ),
        }

    prepared_rows, preflight_issues = _prepare_reference_rows(
        source_key,
        source_rows,
    )

    warning_count = sum(
        1 for item in preflight_issues
        if item.get("severity") == "WARNING"
    )
    error_count = sum(
        1 for item in preflight_issues
        if item.get("severity") == "ERROR"
    )

    issue_counts: dict[str, int] = {}
    for item in preflight_issues:
        code = item["code"]
        issue_counts[code] = issue_counts.get(code, 0) + 1

    valid_rows = 0
    invalid_rows = 0
    for row in prepared_rows:
        error = _preview_row_error(source_key, row)
        if error:
            invalid_rows += 1
            issue_counts["ROW_VALIDATION"] = (
                issue_counts.get("ROW_VALIDATION", 0) + 1
            )
        else:
            valid_rows += 1

    skipped = warning_count + invalid_rows
    errors = error_count

    return {
        "source": source_key,
        "status": (
            "READY"
            if errors == 0 and valid_rows > 0
            else "WARNING"
            if valid_rows > 0
            else "BLOCKED"
        ),
        "rows_read": len(source_rows),
        "rows_ready": valid_rows,
        "rows_skipped": skipped,
        "rows_error": errors,
        "issue_counts": issue_counts,
        "message": (
            f"Готово к загрузке: {valid_rows} из {len(source_rows)}"
        ),
    }


async def sync_reference(source_key: str) -> dict:
    if source_key not in REFERENCE_SOURCES:
        raise KeyError(source_key)

    source = REFERENCE_SOURCES[source_key]
    client = CoverseClient()
    try:
        cells = await client.read_range(source.document_id, source.sheet_name, source.range_a1)
    finally:
        await client.close()

    header, rows = parse_reference_rows(source, cells)
    source_rows_read = len(rows)
    rows, preflight_issues = _prepare_reference_rows(source_key, rows)

    with engine.begin() as connection:
        log_id = _start_log(connection, source)
        previous_issues_resolved = _resolve_previous_issues(
            connection,
            source,
        )

        missing_headers = validate_headers(source, header)
        if missing_headers:
            message = f"Источник заблокирован: отсутствуют обязательные заголовки: {', '.join(missing_headers)}"
            _issue(connection, source, None, "INVALID_SOURCE_SCHEMA", message, {"header": header})
            _finish_log(
                connection,
                log_id,
                status="BLOCKED",
                rows_read=source_rows_read,
                rows_applied=0,
                rows_skipped=len(rows),
                rows_error=0,
                message=message,
                details={
                    "header": header,
                    "missing_headers": missing_headers,
                    "previous_issues_resolved": previous_issues_resolved,
                },
            )
            return {
                "source": source_key,
                "status": "BLOCKED",
                "rows_read": source_rows_read,
                "rows_applied": 0,
                "message": message,
            }

        for item in preflight_issues:
            _issue(
                connection,
                source,
                item.get("row_number"),
                item["code"],
                item["message"],
                item.get("raw_data"),
                severity=item.get("severity", "ERROR"),
            )

        handler = HANDLERS.get(source_key)
        if handler is None:
            message = "Источник пока не имеет безопасного обработчика"
            _finish_log(
                connection,
                log_id,
                status="BLOCKED",
                rows_read=source_rows_read,
                rows_applied=0,
                rows_skipped=len(rows),
                rows_error=0,
                message=message,
            )
            return {"source": source_key, "status": "BLOCKED", "message": message}

        applied = 0
        skipped = sum(
            1 for item in preflight_issues
            if item.get("severity") == "WARNING"
        )
        errors = sum(
            1 for item in preflight_issues
            if item.get("severity") == "ERROR"
        )

        for row in rows:
            try:
                handler(connection, row)
                applied += 1
            except ValueError as exc:
                skipped += 1
                _issue(connection, source, row.get("source_row"), "ROW_VALIDATION", str(exc), row, severity="WARNING")
            except Exception as exc:
                errors += 1
                _issue(connection, source, row.get("source_row"), "ROW_ERROR", str(exc), row)

        status = "COMPLETED" if errors == 0 else "COMPLETED_WITH_ERRORS"
        _finish_log(
            connection,
            log_id,
            status=status,
            rows_read=source_rows_read,
            rows_applied=applied,
            rows_skipped=skipped,
            rows_error=errors,
            details={
                "previous_issues_resolved": previous_issues_resolved,
            },
        )

        return {
            "source": source_key,
            "status": status,
            "rows_read": source_rows_read,
            "rows_applied": applied,
            "rows_skipped": skipped,
            "rows_error": errors,
        }


async def sync_all_references() -> dict:
    results = {}
    for key in ("employees", "equipment", "products", "tariffs", "production_norms"):
        try:
            results[key] = await sync_reference(key)
        except Exception as exc:
            results[key] = {"source": key, "status": "FAILED", "message": str(exc)}
    return results


PILOT_SOURCE_ORDER = ("equipment", "employees", "products", "tariffs")


async def pilot_sync_references() -> dict:
    """Safely run the first pilot master-data load in dependency-aware order.

    Every source is previewed before write. Blocked sources are skipped.
    Production norms are intentionally excluded until their Coverse schema
    contains stable identifying keys.
    """
    previews: dict[str, dict] = {}
    results: dict[str, dict] = {}

    for key in PILOT_SOURCE_ORDER:
        try:
            preview = await preview_reference(key)
            previews[key] = preview

            if preview.get("status") == "BLOCKED":
                results[key] = {
                    "source": key,
                    "status": "SKIPPED",
                    "message": preview.get("message") or "Источник заблокирован preview-проверкой",
                }
                continue

            results[key] = await sync_reference(key)
        except Exception as exc:
            results[key] = {
                "source": key,
                "status": "FAILED",
                "message": str(exc),
            }

    results["production_norms"] = {
        "source": "production_norms",
        "status": "SKIPPED",
        "message": (
            "Нормы Coverse не загружаются в пилоте до исправления схемы; "
            "используется ERP-норма или ручной резервный норматив."
        ),
    }

    failed = sum(1 for item in results.values() if item.get("status") == "FAILED")
    skipped = sum(1 for item in results.values() if item.get("status") == "SKIPPED")
    completed_with_errors = sum(
        1 for item in results.values()
        if item.get("status") == "COMPLETED_WITH_ERRORS"
    )

    overall_status = (
        "FAILED"
        if failed
        else "COMPLETED_WITH_WARNINGS"
        if skipped or completed_with_errors
        else "COMPLETED"
    )

    return {
        "status": overall_status,
        "message": (
            "Пилотная загрузка справочников завершена. "
            f"Ошибок: {failed}; пропущено источников: {skipped}; "
            f"источников с ошибками строк: {completed_with_errors}."
        ),
        "order": list(PILOT_SOURCE_ORDER),
        "previews": previews,
        "results": results,
    }
