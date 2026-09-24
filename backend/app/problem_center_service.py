from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import settings
from .database import engine
from .integration_status import integration_dashboard
from .oee_service import current_business_shift
from .shift_master_service import shift_master_dashboard


SEVERITY_ORDER = {
    "CRITICAL": 0,
    "WARNING": 1,
    "INFO": 2,
}


def _item(
    key: str,
    severity: str,
    source: str,
    title: str,
    message: str,
    owner_role: str,
    target_section: str,
    business_date: str | None = None,
    shift_code: str | None = None,
    equipment_code: str | None = None,
    production_run_id: str | None = None,
) -> dict:
    return {
        "key": key,
        "severity": severity,
        "source": source,
        "title": title,
        "message": message,
        "owner_role": owner_role,
        "target_section": target_section,
        "business_date": business_date,
        "shift_code": shift_code,
        "equipment_code": equipment_code,
        "production_run_id": production_run_id,
    }


def _overdue_open_shifts(now: datetime) -> list[dict]:
    cutoff = now.date() - timedelta(days=14)
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    s.id,
                    s.business_date,
                    s.ended_at,
                    st.code AS shift_code,
                    st.name AS shift_name
                FROM shifts s
                JOIN shift_types st ON st.id = s.shift_type_id
                WHERE s.status = 'OPEN'
                  AND s.ended_at < :now
                  AND s.business_date >= :cutoff
                ORDER BY s.ended_at
                """
            ),
            {
                "now": now,
                "cutoff": cutoff,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def problem_center(
    business_date: date | None = None,
    shift_code: str | None = None,
) -> dict:
    if business_date is None and shift_code is None:
        business_date, shift_code = current_business_shift()
    else:
        current_date, current_shift = current_business_shift()
        business_date = business_date or current_date
        shift_code = (shift_code or current_shift).upper()

    dashboard = shift_master_dashboard(
        business_date,
        shift_code,
    )
    integration = integration_dashboard()
    now = datetime.now(ZoneInfo(settings.business_timezone))
    items = []

    for line in dashboard["lines"]:
        for alert in line.get("alerts", []):
            alert_type = alert["type"]
            severity = alert["severity"]

            if alert_type == "DOWNTIME":
                title = "Активный простой"
                owner = "SHIFT_MASTER"
                target = "shift-master"
            elif alert_type == "PACE":
                title = "Отставание от планового темпа"
                owner = "SHIFT_MASTER"
                target = "shift-master"
            elif alert_type == "MISSING_NORM":
                title = "Отсутствует норматив скорости"
                owner = "PRODUCTION_MANAGER"
                target = "erp-plan"
            else:
                title = "Расхождение по учету"
                owner = "SHIFT_MASTER"
                target = "shift-control"

            items.append(
                _item(
                    key=(
                        f"{alert_type}:{line['production_run_id']}:"
                        f"{business_date.isoformat()}:{shift_code}"
                    ),
                    severity=severity,
                    source="PRODUCTION",
                    title=title,
                    message=(
                        f"{line['equipment_code']} · "
                        f"{line['order_no'] or 'без заказа'} · "
                        f"{alert['message']}"
                    ),
                    owner_role=owner,
                    target_section=target,
                    business_date=business_date.isoformat(),
                    shift_code=shift_code,
                    equipment_code=line["equipment_code"],
                    production_run_id=line["production_run_id"],
                )
            )

    shift_status = dashboard["shift"].get("status")
    if shift_status == "OPEN" and now >= dashboard["shift"]["ended_at"]:
        items.append(
            _item(
                key=f"SHIFT_OVERDUE:{dashboard['shift'].get('id')}",
                severity="CRITICAL",
                source="SHIFT",
                title="Смена не закрыта",
                message=(
                    f"{dashboard['shift']['label']} "
                    f"{dashboard['shift']['business_date']} "
                    "завершилась, но статус остается OPEN"
                ),
                owner_role="SHIFT_MASTER",
                target_section="shift-master",
                business_date=business_date.isoformat(),
                shift_code=shift_code,
            )
        )

    for row in _overdue_open_shifts(now):
        key = f"SHIFT_OVERDUE:{row['id']}"
        if any(item["key"] == key for item in items):
            continue
        items.append(
            _item(
                key=key,
                severity="CRITICAL",
                source="SHIFT",
                title="Просроченная незакрытая смена",
                message=(
                    f"{row['business_date']} · {row['shift_code']} · "
                    "смена завершена по времени, но не закрыта"
                ),
                owner_role="SHIFT_MASTER",
                target_section="shift-master",
                business_date=row["business_date"].isoformat(),
                shift_code=row["shift_code"],
            )
        )

    totals = integration.get("totals", {})
    unresolved = int(totals.get("unresolved") or 0)
    resolution_issues = int(
        totals.get("open_resolution_issues") or 0
    )
    master_issues = int(totals.get("open_master_issues") or 0)

    if unresolved > 0:
        items.append(
            _item(
                key="INTEGRATION:UNRESOLVED",
                severity="WARNING",
                source="INTEGRATION",
                title="Есть несопоставленные события",
                message=f"Не сопоставлено событий: {unresolved}",
                owner_role="ADMIN",
                target_section="integrations",
            )
        )

    if resolution_issues > 0:
        items.append(
            _item(
                key="INTEGRATION:RESOLUTION_ISSUES",
                severity="WARNING",
                source="INTEGRATION",
                title="Требуется ручное сопоставление",
                message=(
                    "Открытых проблем сопоставления: "
                    f"{resolution_issues}"
                ),
                owner_role="ADMIN",
                target_section="integrations",
            )
        )

    if master_issues > 0:
        items.append(
            _item(
                key="INTEGRATION:MASTER_ISSUES",
                severity="CRITICAL",
                source="INTEGRATION",
                title="Ошибка справочников",
                message=(
                    "Открытых ошибок синхронизации справочников: "
                    f"{master_issues}"
                ),
                owner_role="ADMIN",
                target_section="integrations",
            )
        )

    for source_key, source in integration.get(
        "master_sources",
        {},
    ).items():
        if source.get("status") in {"FAILED", "BLOCKED"}:
            items.append(
                _item(
                    key=f"MASTER_SOURCE:{source_key}",
                    severity="CRITICAL",
                    source="INTEGRATION",
                    title="Источник справочника заблокирован",
                    message=(
                        f"{source_key}: "
                        f"{source.get('message') or source.get('status')}"
                    ),
                    owner_role="ADMIN",
                    target_section="integrations",
                )
            )

    items.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["source"],
            item["equipment_code"] or "",
            item["title"],
        )
    )

    return {
        "context": {
            "business_date": business_date.isoformat(),
            "shift_code": shift_code,
        },
        "summary": {
            "total": len(items),
            "critical": sum(
                1 for item in items
                if item["severity"] == "CRITICAL"
            ),
            "warning": sum(
                1 for item in items
                if item["severity"] == "WARNING"
            ),
            "production": sum(
                1 for item in items
                if item["source"] == "PRODUCTION"
            ),
            "integration": sum(
                1 for item in items
                if item["source"] == "INTEGRATION"
            ),
            "shift": sum(
                1 for item in items
                if item["source"] == "SHIFT"
            ),
        },
        "items": items,
    }
