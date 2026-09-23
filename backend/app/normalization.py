from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .config import settings


def parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_time(value) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass
    return None


def parse_response_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(settings.business_timezone))
    return dt


def derive_shift(
    date_value,
    time_value,
    *,
    date_is_business_date: bool,
    explicit_shift: str | None = None,
) -> dict | None:
    d = parse_date(date_value)
    t = parse_time(time_value)
    if d is None:
        return None

    explicit = (explicit_shift or "").strip().upper()
    if explicit in {"ДЕНЬ", "DAY"}:
        code = "DAY"
        business_date = d
    elif explicit in {"НОЧЬ", "NIGHT"}:
        code = "NIGHT"
        business_date = d
    elif t is None:
        code = None
        business_date = d
    elif time(9, 0) <= t < time(21, 0):
        code = "DAY"
        business_date = d
    else:
        code = "NIGHT"
        if date_is_business_date:
            business_date = d
        else:
            business_date = d if t >= time(21, 0) else d - timedelta(days=1)

    tz = ZoneInfo(settings.business_timezone)
    if code == "DAY":
        shift_start = datetime.combine(business_date, time(9, 0), tzinfo=tz)
        shift_end = datetime.combine(business_date, time(21, 0), tzinfo=tz)
    elif code == "NIGHT":
        shift_start = datetime.combine(business_date, time(21, 0), tzinfo=tz)
        shift_end = datetime.combine(business_date + timedelta(days=1), time(9, 0), tzinfo=tz)
    else:
        shift_start = None
        shift_end = None

    occurred_at = combine_event_time(
        d,
        t,
        business_date=business_date,
        shift_code=code,
        date_is_business_date=date_is_business_date,
    )

    return {
        "business_date": business_date,
        "shift_code": code,
        "shift_start": shift_start,
        "shift_end": shift_end,
        "occurred_at": occurred_at,
    }


def combine_event_time(
    source_date: date | None,
    source_time: time | None,
    *,
    business_date: date | None,
    shift_code: str | None,
    date_is_business_date: bool,
) -> datetime | None:
    if source_date is None or source_time is None:
        return None

    calendar_date = source_date
    if date_is_business_date and shift_code == "NIGHT" and source_time < time(9, 0):
        calendar_date = source_date + timedelta(days=1)

    return datetime.combine(
        calendar_date,
        source_time,
        tzinfo=ZoneInfo(settings.business_timezone),
    )


def normalized_personnel_number(value) -> str | None:
    if value is None:
        return None
    text = "".join(ch for ch in str(value).strip() if ch.isdigit())
    if not text:
        return None
    return text.zfill(5)


def normalized_code(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.upper() if text else None


def normalized_external_key(row: dict) -> str:
    return "|".join(
        [
            str(row.get("source_document_id") or ""),
            str(row.get("source_sheet") or ""),
            str(row.get("source_row") or ""),
            str(row.get("response_at") or ""),
        ]
    )


def normalize_coverse_event(source_key: str, row: dict, date_is_business_date: bool) -> dict:
    response_at = parse_response_datetime(row.get("response_at"))
    ended_at = None
    good_quantity = None

    if source_key == "downtime":
        shift = derive_shift(row.get("shift_date"), row.get("time_from"), date_is_business_date=True)
        end_time = parse_time(row.get("time_to"))
        end_date = parse_date(row.get("shift_date"))
        if shift and end_date and end_time:
            ended_at = combine_event_time(
                end_date,
                end_time,
                business_date=shift["business_date"],
                shift_code=shift["shift_code"],
                date_is_business_date=True,
            )
            if ended_at and shift["occurred_at"] and ended_at <= shift["occurred_at"]:
                ended_at += timedelta(days=1)
        quantity = None
        secondary_quantity = None
        article_code = None
        order_no = None

    elif source_key == "production_output":
        shift = derive_shift(row.get("shift_date"), row.get("started_at"), date_is_business_date=True)
        end_time = parse_time(row.get("ended_at"))
        end_date = parse_date(row.get("shift_date"))
        if shift and end_date and end_time:
            ended_at = combine_event_time(
                end_date,
                end_time,
                business_date=shift["business_date"],
                shift_code=shift["shift_code"],
                date_is_business_date=True,
            )
            if ended_at and shift["occurred_at"] and ended_at <= shift["occurred_at"]:
                ended_at += timedelta(days=1)
        quantity = parse_decimal(row.get("counter_qty"))
        secondary_quantity = parse_decimal(row.get("defect_qty"))
        good_quantity = parse_decimal(row.get("good_product_qty"))
        article_code = None
        order_no = normalized_code(row.get("order_no"))

    elif source_key == "qc_defects":
        shift = derive_shift(
            row.get("shift_date"),
            row.get("accepted_at"),
            date_is_business_date=True,
            explicit_shift=row.get("shift"),
        )
        quantity = parse_decimal(row.get("defect_qty"))
        secondary_quantity = None
        article_code = None
        order_no = None

    elif source_key in {"warehouse", "accountant"}:
        shift = derive_shift(row.get("calendar_date"), row.get("accepted_at"), date_is_business_date=False)
        packages = parse_decimal(row.get("packages_qty"))
        per_package = parse_decimal(row.get("qty_per_package"))
        quantity = packages * per_package if packages is not None and per_package is not None else None
        secondary_quantity = packages
        good_quantity = quantity
        article_code = normalized_code(row.get("article_code"))
        order_no = None

    else:
        shift = None
        quantity = None
        secondary_quantity = None
        article_code = None
        order_no = None

    return {
        "source_system": "COVERSE",
        "event_type": source_key,
        "source_document_id": row.get("source_document_id"),
        "source_sheet": row.get("source_sheet"),
        "source_row": row.get("source_row"),
        "source_record_key": normalized_external_key(row),
        "response_at": response_at,
        "business_date": shift.get("business_date") if shift else None,
        "shift_code": shift.get("shift_code") if shift else None,
        "occurred_at": shift.get("occurred_at") if shift else response_at,
        "ended_at": ended_at,
        "personnel_number": normalized_personnel_number(row.get("personnel_number")),
        "equipment_code": normalized_code(row.get("equipment_code")),
        "order_no": order_no,
        "article_code": article_code,
        "ticket_no": row.get("ticket_no"),
        "quantity": quantity,
        "secondary_quantity": secondary_quantity,
        "good_quantity": good_quantity,
        "payload": row,
    }
