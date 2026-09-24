from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings


@dataclass(frozen=True)
class CoverseSource:
    key: str
    document_id: str
    sheet_name: str
    range_a1: str
    date_is_business_date: bool
    columns: dict[str, int]


SOURCES: dict[str, CoverseSource] = {
    "downtime": CoverseSource(
        key="downtime",
        document_id="1c2ecf5f-4698-43ef-98bc-b9e50ef4950e",
        sheet_name="Лист 1",
        range_a1="A:I",
        date_is_business_date=True,
        columns={
            "response_at": 0,
            "personnel_number": 1,
            "equipment_code": 2,
            "shift_date": 3,
            "time_from": 4,
            "time_to": 5,
            "reason": 6,
            "master": 7,
            "comment": 8,
        },
    ),
    "production_output": CoverseSource(
        key="production_output",
        document_id="65983c39-1ab2-485e-847e-2b739ee46e5a",
        sheet_name="Лист 1",
        range_a1="A:L",
        date_is_business_date=True,
        columns={
            "response_at": 0,
            "personnel_number": 1,
            "shift_date": 2,
            "order_no": 3,
            "started_at": 4,
            "ended_at": 5,
            "counter_qty": 6,
            "defect_qty": 7,
            "defect_kg": 8,
            "good_product_qty": 9,
            "boxes_qty": 10,
            "pallets_qty": 11,
        },
    ),
    "qc_defects": CoverseSource(
        key="qc_defects",
        document_id="bab2fb73-e435-4c3a-8d93-e5a24cba39a9",
        sheet_name="Лист 1",
        range_a1="A:F",
        date_is_business_date=True,
        columns={
            "response_at": 0,
            "personnel_number": 1,
            "shift_date": 2,
            "shift": 3,
            "accepted_at": 4,
            "defect_qty": 5,
        },
    ),
    "warehouse": CoverseSource(
        key="warehouse",
        document_id="8e3e432c-7489-42e3-b45d-488c64219f7f",
        sheet_name="Лист 1",
        range_a1="A:H",
        date_is_business_date=False,
        columns={
            "response_at": 0,
            "ticket_no": 1,
            "personnel_number": 2,
            "calendar_date": 3,
            "accepted_at": 4,
            "article_code": 5,
            "packages_qty": 6,
            "qty_per_package": 7,
        },
    ),
    "accountant": CoverseSource(
        key="accountant",
        document_id="64add4fb-f8a0-417d-b813-93257c3f9f5d",
        sheet_name="Лист 1",
        range_a1="A:J",
        date_is_business_date=False,
        columns={
            "response_at": 0,
            "ticket_no_fallback": 1,
            "personnel_number": 2,
            "equipment_code": 3,
            "calendar_date": 4,
            "accepted_at": 5,
            "article_code": 6,
            "packages_qty": 7,
            "qty_per_package": 8,
            "ticket_no": 9,
        },
    ),
}


def _cell_value(cell: Any) -> Any:
    if cell is None:
        return None
    if isinstance(cell, dict):
        return cell.get("formatted") or cell.get("value")
    return cell


def normalize_rows(source: CoverseSource, cells: list[list[Any]]) -> list[dict[str, Any]]:
    if not cells:
        return []

    rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(cells[1:], start=2):
        if not row or all(_cell_value(cell) in (None, "") for cell in row):
            continue

        item: dict[str, Any] = {
            "source_system": "COVERSE",
            "source_document_id": source.document_id,
            "source_sheet": source.sheet_name,
            "source_row": row_number,
            "source_key": source.key,
        }
        for field_name, index in source.columns.items():
            item[field_name] = _cell_value(row[index]) if index < len(row) else None

        if source.key == "accountant" and not item.get("ticket_no"):
            item["ticket_no"] = item.get("ticket_no_fallback")

        rows.append(item)
    return rows


class CoverseClient:
    def __init__(self) -> None:
        if not settings.coverse_api_token:
            raise RuntimeError("COVERSE_API_TOKEN is not configured")

        self.client = httpx.AsyncClient(
            base_url=settings.coverse_api_base_url.rstrip("/"),
            timeout=30,
            headers={
                "Authorization": f"Bearer {settings.coverse_api_token}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _extract_cells_and_pagination(payload: dict[str, Any]) -> tuple[list[list[Any]], dict[str, Any]]:
        value_range = payload.get("values")

        if isinstance(value_range, dict):
            cells = value_range.get("cells") or []
            pagination = value_range.get("pagination") or payload.get("pagination") or {}
            return cells, pagination

        if isinstance(payload.get("cells"), list):
            return payload.get("cells") or [], payload.get("pagination") or {}

        if isinstance(value_range, list):
            return value_range, payload.get("pagination") or {}

        return [], payload.get("pagination") or {}

    async def read_range(
        self,
        document_id: str,
        sheet_name: str,
        range_a1: str,
        *,
        page_size: int = 1000,
    ) -> list[list[Any]]:
        endpoint = settings.coverse_read_range_path.format(document_id=document_id)
        offset = 0
        all_cells: list[list[Any]] = []

        while True:
            response = await self.client.get(
                endpoint,
                params={
                    "range": f"'{sheet_name}'!{range_a1}",
                    "offset": offset,
                    "limit": page_size,
                },
            )
            response.raise_for_status()
            payload = response.json()
            cells, pagination = self._extract_cells_and_pagination(payload)

            if offset > 0 and cells:
                # Coverse can return the header again for some range forms.
                # Do not duplicate it when it is byte-for-byte identical.
                if all_cells and cells[0] == all_cells[0]:
                    cells = cells[1:]

            all_cells.extend(cells)

            has_more = pagination.get("hasMore")
            next_offset = pagination.get("nextOffset")
            returned = pagination.get("returned")

            if has_more is False:
                break

            if next_offset is not None:
                next_offset = int(next_offset)
                if next_offset <= offset:
                    break
                offset = next_offset
                continue

            page_count = int(returned) if returned is not None else len(cells)
            if page_count <= 0 or page_count < page_size:
                break

            offset += page_count

        return all_cells

    async def read_source(self, key: str) -> list[dict[str, Any]]:
        source = SOURCES[key]
        cells = await self.read_range(source.document_id, source.sheet_name, source.range_a1)
        return normalize_rows(source, cells)
