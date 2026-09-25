from dataclasses import dataclass
from typing import Any

from .integrations.coverse import _cell_value


@dataclass(frozen=True)
class ReferenceSource:
    key: str
    document_id: str
    sheet_name: str
    range_a1: str
    columns: dict[str, int]
    required_headers: tuple[str, ...]


REFERENCE_SOURCES: dict[str, ReferenceSource] = {
    "employees": ReferenceSource(
        key="employees",
        document_id="d519a1ec-f251-41db-92e4-e4c5d5b9c3d8",
        sheet_name="Лист 1",
        range_a1="A1:G1000",
        columns={
            "department_name": 1,
            "full_name": 2,
            "personnel_number": 3,
            "position_name": 4,
        },
        required_headers=("Сотрудник", "Табельный номер", "Должность"),
    ),
    "equipment": ReferenceSource(
        key="equipment",
        document_id="cb08fd21-0624-4fc6-9050-b4146f2f6fbb",
        sheet_name="СПРАВОЧНИК_ЛИНИЙ",
        range_a1="A:H",
        columns={
            "name": 0,
            "status": 1,
            "canonical_form_name": 4,
            "norm_name": 5,
            "tariff_name": 6,
            "comment": 7,
        },
        required_headers=("Наименование линии", "Статус"),
    ),
    "products": ReferenceSource(
        key="products",
        document_id="cb08fd21-0624-4fc6-9050-b4146f2f6fbb",
        sheet_name="Таблица соответствия складского кода и артикула",
        range_a1="A:G",
        columns={
            "product_kind": 1,
            "name": 2,
            "article": 3,
            "warehouse_code": 4,
            "combined_article": 5,
            "status": 6,
        },
        required_headers=("Наименование продукции", "Артикул", "Складской код"),
    ),
    "tariffs": ReferenceSource(
        key="tariffs",
        document_id="cb08fd21-0624-4fc6-9050-b4146f2f6fbb",
        sheet_name="ТАРИФНАЯ_СЕТКА_2026",
        range_a1="A:J",
        columns={
            "accrual_type": 0,
            "role_name": 1,
            "equipment_code": 2,
            "product_type": 3,
            "print_flag": 4,
            "tariff_group": 5,
            "unit": 6,
            "rate": 7,
            "payment_type": 8,
            "valid_from": 9,
        },
        required_headers=("Тип начисления", "Машина", "Ставка", "Дата начала"),
    ),
    "production_norms": ReferenceSource(
        key="production_norms",
        document_id="cb08fd21-0624-4fc6-9050-b4146f2f6fbb",
        sheet_name="СПРАВОЧНИК_НОРМ_ВЫПУСКА",
        range_a1="A:Z",
        columns={},
        required_headers=("Машина", "Норма"),
    ),
}


def parse_reference_rows(source: ReferenceSource, cells: list[list[Any]]) -> tuple[list[str], list[dict]]:
    if not cells:
        return [], []

    header = [str(_cell_value(cell) or "").strip() for cell in cells[0]]
    rows: list[dict] = []

    for row_number, row in enumerate(cells[1:], start=2):
        if not row or all(_cell_value(cell) in (None, "") for cell in row):
            continue
        item = {
            "source_row": row_number,
            "source_document_id": source.document_id,
            "source_sheet": source.sheet_name,
        }
        for name, index in source.columns.items():
            item[name] = _cell_value(row[index]) if index < len(row) else None
        rows.append(item)

    return header, rows


def validate_headers(source: ReferenceSource, header: list[str]) -> list[str]:
    normalized = {item.strip().lower() for item in header if item}
    missing = [
        expected
        for expected in source.required_headers
        if expected.strip().lower() not in normalized
    ]
    return missing
