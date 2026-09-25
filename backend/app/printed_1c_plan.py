from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    raw = _text(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _execution_datetime(value: Any) -> tuple[datetime | None, bool]:
    if value is None or value == "":
        return None, False
    if isinstance(value, datetime):
        return value, True
    if isinstance(value, date):
        return datetime.combine(value, time.min), False

    raw = _text(value)
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt), True
        except ValueError:
            pass

    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed, False
        except ValueError:
            pass

    return None, False


def _shift_from_execution(
    execution_at: datetime | None,
    has_time: bool,
) -> tuple[date | None, str | None]:
    if execution_at is None:
        return None, None

    if not has_time:
        return execution_at.date(), None

    value_time = execution_at.time()
    if value_time < time(9, 0):
        return execution_at.date() - timedelta(days=1), "NIGHT"
    if value_time < time(21, 0):
        return execution_at.date(), "DAY"
    return execution_at.date(), "NIGHT"


def _first_right(row: list[Any], column_index: int):
    for value in row[column_index + 1:]:
        if value not in (None, ""):
            return value
    return None


def _label_value(rows: list[list[Any]], label: str):
    target = label.strip().lower()
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            if _text(value).lower() == target:
                return _first_right(row, column_index), row_index + 1, column_index + 1
    return None, None, None


def _find_regex(rows: list[list[Any]], pattern: str):
    expression = re.compile(pattern, re.IGNORECASE)
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            if value in (None, ""):
                continue
            text_value = _text(value)
            match = expression.search(text_value)
            if match:
                return match, row_index + 1, column_index + 1, text_value
    return None, None, None, None


def detect_printed_1c_form(rows: list[list[Any]]) -> bool:
    match, *_ = _find_regex(
        rows[:12],
        r"Задание\s+на\s+производство\s+№",
    )
    return match is not None


def _find_section_row(rows: list[list[Any]], title: str) -> int | None:
    for index, row in enumerate(rows):
        if any(_text(value) == title for value in row):
            return index
    return None


def _header_columns(row: list[Any]) -> dict[str, int]:
    return {
        _text(value): index
        for index, value in enumerate(row)
        if _text(value)
    }


def _route_operations(rows: list[list[Any]]) -> list[dict[str, Any]]:
    route_index = _find_section_row(rows, "Маршрутный лист")
    if route_index is None:
        return []

    header_index = None
    columns: dict[str, int] = {}
    for index in range(route_index + 1, min(len(rows), route_index + 10)):
        headers = _header_columns(rows[index])
        if "Операция" in headers and "Исполнитель" in headers:
            header_index = index
            columns = headers
            break

    if header_index is None:
        return []

    result = []
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        operation_col = columns.get("Операция")
        if operation_col is None or operation_col >= len(row):
            continue
        operation = row[operation_col]
        if operation in (None, ""):
            continue

        executor_col = columns.get("Исполнитель")
        hours_col = columns.get("Время (н/ч)")
        executor = row[executor_col] if executor_col is not None and executor_col < len(row) else None
        norm_hours = _decimal(row[hours_col]) if hours_col is not None and hours_col < len(row) else None

        hint = None
        if executor:
            match = re.match(r"\s*([^/]+(?:/[^/]+)?)//", _text(executor))
            if match:
                hint = match.group(1).strip()

        result.append(
            {
                "source_row": index + 1,
                "operation_name": _text(operation),
                "equipment_source_name": _text(executor) or None,
                "equipment_hint": hint,
                "norm_hours": norm_hours,
            }
        )
    return result


def parse_printed_1c_form(rows: list[list[Any]]) -> dict[str, Any]:
    if not detect_printed_1c_form(rows):
        raise ValueError("Not a printed 1C production task form")

    task_match, *_ = _find_regex(
        rows,
        r"Задание\s+на\s+производство\s+№\s*(.+)$",
    )
    task_id = task_match.group(1).strip() if task_match else None

    order_raw, _, _ = _label_value(rows, "Заказ:")
    order_match = re.search(
        r"Заказ\s+на\s+производство\s+(.+?)\s+от\s+",
        _text(order_raw),
        re.IGNORECASE,
    )
    order_no = order_match.group(1).strip() if order_match else (_text(order_raw) or None)

    execution_date_raw, _, _ = _label_value(rows, "Дата выполнения:")
    execution_at, execution_has_time = _execution_datetime(execution_date_raw)
    business_date, shift_code = _shift_from_execution(
        execution_at,
        execution_has_time,
    )

    workshop, _, _ = _label_value(rows, "Подразделение:")
    product_name, _, _ = _label_value(rows, "Изделие:")
    specification, _, _ = _label_value(rows, "Спецификация:")
    plan_qty_header, _, _ = _label_value(rows, "Количество (шт):")
    plan_qty_header = _decimal(plan_qty_header)

    operations = _route_operations(rows)

    output_index = _find_section_row(rows, "Выходные изделия")
    outputs: list[dict[str, Any]] = []

    if output_index is not None:
        header_index = None
        columns: dict[str, int] = {}
        for index in range(output_index + 1, min(len(rows), output_index + 10)):
            headers = _header_columns(rows[index])
            if "Артикул" in headers and "План" in headers:
                header_index = index
                columns = headers
                break

        if header_index is not None:
            for index in range(header_index + 1, len(rows)):
                row = rows[index]
                if any(_text(value) == "Маршрутный лист" for value in row):
                    break

                article_col = columns.get("Артикул")
                if article_col is None or article_col >= len(row):
                    continue

                article = row[article_col]
                if article in (None, ""):
                    continue

                product_col = columns.get("Изделие")
                unit_col = columns.get("Ед. изм.")
                plan_col = columns.get("План")

                row_product = row[product_col] if product_col is not None and product_col < len(row) else None
                unit = row[unit_col] if unit_col is not None and unit_col < len(row) else None
                plan_qty = _decimal(row[plan_col]) if plan_col is not None and plan_col < len(row) else None

                primary_operation = operations[0] if operations else {}
                ideal_rate = None
                norm_hours = primary_operation.get("norm_hours")
                if (
                    plan_qty is not None
                    and norm_hours is not None
                    and norm_hours > 0
                    and _text(unit).lower() in {"шт", "pcs", "piece", "pieces"}
                ):
                    ideal_rate = plan_qty / norm_hours

                outputs.append(
                    {
                        "source_row": index + 1,
                        "erp_guid": None,
                        "task_id": task_id,
                        "business_date": business_date,
                        "shift_code": shift_code,
                        "workshop": _text(workshop) or None,
                        "equipment_code": None,
                        "order_no": order_no,
                        "article": _text(article) or None,
                        "customer": None,
                        "tech_card": _text(specification) or None,
                        "plan_qty_pcs": plan_qty if _text(unit).lower() == "шт" else plan_qty_header,
                        "pcs_per_box": None,
                        "boxes_per_pallet": None,
                        "plan_kg": plan_qty if _text(unit).lower() == "кг" else None,
                        "source_status": None,
                        "product_name": _text(row_product) or _text(product_name) or None,
                        "output_unit": _text(unit) or None,
                        "route_operation": primary_operation.get("operation_name"),
                        "route_equipment_name": primary_operation.get("equipment_source_name"),
                        "route_equipment_hint": primary_operation.get("equipment_hint"),
                        "norm_hours": norm_hours,
                        "ideal_rate_per_hour": ideal_rate,
                        "route_operations": operations,
                    }
                )

    if not outputs:
        primary_operation = operations[0] if operations else {}
        ideal_rate = None
        norm_hours = primary_operation.get("norm_hours")
        if plan_qty_header is not None and norm_hours is not None and norm_hours > 0:
            ideal_rate = plan_qty_header / norm_hours

        outputs.append(
            {
                "source_row": 1,
                "erp_guid": None,
                "task_id": task_id,
                "business_date": business_date,
                "shift_code": shift_code,
                "workshop": _text(workshop) or None,
                "equipment_code": None,
                "order_no": order_no,
                "article": None,
                "customer": None,
                "tech_card": _text(specification) or None,
                "plan_qty_pcs": plan_qty_header,
                "pcs_per_box": None,
                "boxes_per_pallet": None,
                "plan_kg": None,
                "source_status": None,
                "product_name": _text(product_name) or None,
                "output_unit": "шт" if plan_qty_header is not None else None,
                "route_operation": primary_operation.get("operation_name"),
                "route_equipment_name": primary_operation.get("equipment_source_name"),
                "route_equipment_hint": primary_operation.get("equipment_hint"),
                "norm_hours": norm_hours,
                "ideal_rate_per_hour": ideal_rate,
                "route_operations": operations,
            }
        )

    return {
        "schema_type": "1C_PRINTED_PRODUCTION_TASK",
        "task_id": task_id,
        "order_no": order_no,
        "business_date": business_date,
        "shift_code": shift_code,
        "execution_at": execution_at,
        "execution_has_time": execution_has_time,
        "workshop": _text(workshop) or None,
        "product_name": _text(product_name) or None,
        "specification": _text(specification) or None,
        "plan_qty_header": plan_qty_header,
        "operations": operations,
        "outputs": outputs,
    }


def inspect_printed_1c_form(rows: list[list[Any]]) -> dict[str, Any]:
    parsed = parse_printed_1c_form(rows)
    return {
        "schema_type": parsed["schema_type"],
        "task_id": parsed["task_id"],
        "order_no": parsed["order_no"],
        "business_date": parsed["business_date"].isoformat() if parsed["business_date"] else None,
        "shift_code": parsed["shift_code"],
        "execution_at": parsed["execution_at"].isoformat(sep=" ") if parsed["execution_at"] else None,
        "workshop": parsed["workshop"],
        "product_name": parsed["product_name"],
        "specification": parsed["specification"],
        "plan_qty_header": str(parsed["plan_qty_header"]) if parsed["plan_qty_header"] is not None else None,
        "outputs": [
            {
                **{
                    key: value
                    for key, value in item.items()
                    if key != "route_operations"
                },
                "plan_qty_pcs": str(item["plan_qty_pcs"]) if item.get("plan_qty_pcs") is not None else None,
                "plan_kg": str(item["plan_kg"]) if item.get("plan_kg") is not None else None,
                "norm_hours": str(item["norm_hours"]) if item.get("norm_hours") is not None else None,
                "ideal_rate_per_hour": str(item["ideal_rate_per_hour"]) if item.get("ideal_rate_per_hour") is not None else None,
            }
            for item in parsed["outputs"]
        ],
        "operations": [
            {
                **item,
                "norm_hours": str(item["norm_hours"]) if item.get("norm_hours") is not None else None,
            }
            for item in parsed["operations"]
        ],
    }
