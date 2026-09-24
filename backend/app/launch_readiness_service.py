from __future__ import annotations

from sqlalchemy import text

from .config import settings
from .database import engine
from .integration_status import integration_dashboard


CORE_ROLES = (
    "ADMIN",
    "OPERATOR",
    "QC",
    "WAREHOUSE",
    "ACCOUNTANT_PRODUCTION",
    "SHIFT_MASTER",
    "PRODUCTION_MANAGER",
)


def _check(
    key: str,
    title: str,
    status: str,
    message: str,
    target_section: str,
    *,
    scope: str = "CORE",
    value=None,
) -> dict:
    return {
        "key": key,
        "title": title,
        "status": status,
        "message": message,
        "target_section": target_section,
        "scope": scope,
        "value": value,
    }


def _coverage(confirmed: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(confirmed / total * 100, 1)


def launch_readiness() -> dict:
    integration = integration_dashboard()

    with engine.begin() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM employees WHERE is_active) AS employees,
                    (SELECT count(*) FROM equipment WHERE is_active) AS equipment,
                    (SELECT count(*) FROM products WHERE is_active) AS products,
                    (SELECT count(*) FROM downtime_reasons WHERE is_active) AS downtime_reasons,
                    (SELECT count(*) FROM defect_reasons WHERE is_active) AS defect_reasons,
                    (SELECT count(*) FROM production_norms
                        WHERE valid_to IS NULL OR valid_to >= current_date) AS production_norms,
                    (SELECT count(*) FROM payroll_rate_rules
                        WHERE is_active
                          AND valid_from <= current_date
                          AND (valid_to IS NULL OR valid_to >= current_date)) AS payroll_rates,
                    (SELECT count(*) FROM product_payroll_attributes
                        WHERE confirmed) AS payroll_products_confirmed,
                    (SELECT count(*) FROM users WHERE is_active) AS active_users
                """
            )
        ).mappings().one()

        role_rows = connection.execute(
            text(
                """
                SELECT
                    r.code,
                    r.name,
                    count(DISTINCT u.id) FILTER (WHERE u.is_active) AS active_users
                FROM roles r
                LEFT JOIN user_roles ur ON ur.role_id = r.id
                LEFT JOIN users u ON u.id = ur.user_id
                GROUP BY r.id
                ORDER BY r.code
                """
            )
        ).mappings().all()
        roles = {
            row["code"]: {
                "name": row["name"],
                "active_users": int(row["active_users"] or 0),
            }
            for row in role_rows
        }

        latest_plan = connection.execute(
            text(
                """
                SELECT
                    status,
                    source_file_name,
                    rows_read,
                    rows_applied,
                    rows_error,
                    completed_at
                FROM erp_plan_import_batches
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()

        plan_rows = connection.execute(
            text(
                """
                SELECT
                    count(*) AS total,
                    count(*) FILTER (
                        WHERE promotion_status = 'RUN_CREATED'
                    ) AS runs_created,
                    count(*) FILTER (
                        WHERE promotion_status IN ('PARTIAL','UNRESOLVED','ERROR')
                    ) AS unresolved
                FROM erp_plan_staging
                """
            )
        ).mappings().one()

        active_products = int(counts["products"] or 0)
        payroll_confirmed = int(
            counts["payroll_products_confirmed"] or 0
        )

    checks = []

    for key, title, count, target in (
        (
            "employees",
            "Сотрудники",
            int(counts["employees"] or 0),
            "integrations",
        ),
        (
            "equipment",
            "Производственные линии",
            int(counts["equipment"] or 0),
            "integrations",
        ),
        (
            "products",
            "Номенклатура",
            int(counts["products"] or 0),
            "integrations",
        ),
    ):
        checks.append(
            _check(
                key,
                title,
                "READY" if count > 0 else "BLOCKED",
                (
                    f"Активных записей: {count}"
                    if count > 0
                    else "Справочник пока пуст"
                ),
                target,
                value=count,
            )
        )

    downtime_count = int(counts["downtime_reasons"] or 0)
    defect_count = int(counts["defect_reasons"] or 0)

    checks.append(
        _check(
            "downtime_reasons",
            "Причины простоев",
            "READY" if downtime_count > 0 else "BLOCKED",
            (
                f"Активных причин: {downtime_count}"
                if downtime_count
                else "Нужно заполнить причины простоев до тестовой смены"
            ),
            "launch-readiness",
            value=downtime_count,
        )
    )
    checks.append(
        _check(
            "defect_reasons",
            "Причины брака",
            "READY" if defect_count > 0 else "BLOCKED",
            (
                f"Активных причин: {defect_count}"
                if defect_count
                else "Нужно заполнить причины брака до тестовой смены"
            ),
            "launch-readiness",
            value=defect_count,
        )
    )

    norms = int(counts["production_norms"] or 0)
    checks.append(
        _check(
            "production_norms",
            "Нормативы скорости",
            "READY" if norms > 0 else "BLOCKED",
            (
                f"Действующих нормативов: {norms}"
                if norms
                else "Без нормативов Performance и OEE не могут быть рассчитаны полностью"
            ),
            "integrations",
            value=norms,
        )
    )

    missing_roles = []
    for role_code in CORE_ROLES:
        role = roles.get(role_code, {"name": role_code, "active_users": 0})
        if role["active_users"] <= 0:
            missing_roles.append(role["name"])

    checks.append(
        _check(
            "core_roles",
            "Пользователи по обязательным ролям",
            "READY" if not missing_roles else "BLOCKED",
            (
                "Все обязательные роли обеспечены"
                if not missing_roles
                else "Нет активных пользователей: " + ", ".join(missing_roles)
            ),
            "users",
            value=len(CORE_ROLES) - len(missing_roles),
        )
    )

    coverse_ready = bool(settings.coverse_api_token)
    checks.append(
        _check(
            "coverse",
            "Coverse",
            "READY" if coverse_ready else "WARNING",
            (
                "API-токен настроен"
                if coverse_ready
                else "Токен будет добавлен только на production-сервере; web-ввод при этом работает"
            ),
            "integrations",
            value=coverse_ready,
        )
    )

    yandex_ready = bool(settings.yandex_plan_public_url)
    checks.append(
        _check(
            "yandex_plan",
            "Источник производственного плана",
            "READY" if yandex_ready else "BLOCKED",
            (
                "Публичный источник Яндекс.Диска настроен"
                if yandex_ready
                else "Ссылка на производственный план должна быть задана на сервере"
            ),
            "erp-plan",
            value=yandex_ready,
        )
    )

    if latest_plan:
        latest_status = latest_plan["status"]
        plan_status = (
            "READY"
            if latest_status in {"COMPLETED", "COMPLETED_WITH_ERRORS"}
            and int(latest_plan["rows_applied"] or 0) > 0
            else "WARNING"
        )
        plan_message = (
            f"{latest_plan['source_file_name'] or 'ERP-план'}: "
            f"применено {int(latest_plan['rows_applied'] or 0)} из "
            f"{int(latest_plan['rows_read'] or 0)}"
        )
    else:
        plan_status = "WARNING"
        plan_message = "План еще не импортировался"

    checks.append(
        _check(
            "erp_plan_import",
            "Первый импорт ERP-плана",
            plan_status,
            plan_message,
            "erp-plan",
            value=int(plan_rows["total"] or 0),
        )
    )

    unresolved = int(
        integration.get("totals", {}).get("unresolved") or 0
    )
    open_resolution = int(
        integration.get("totals", {}).get("open_resolution_issues") or 0
    )
    checks.append(
        _check(
            "integration_resolution",
            "Сопоставление входящих данных",
            "READY" if unresolved == 0 and open_resolution == 0 else "WARNING",
            (
                "Открытых проблем сопоставления нет"
                if unresolved == 0 and open_resolution == 0
                else (
                    f"Несопоставленных событий: {unresolved}; "
                    f"открытых проблем: {open_resolution}"
                )
            ),
            "integrations",
            value=unresolved + open_resolution,
        )
    )

    master_issues = int(
        integration.get("totals", {}).get("open_master_issues") or 0
    )
    checks.append(
        _check(
            "master_issues",
            "Ошибки справочников",
            "READY" if master_issues == 0 else "WARNING",
            (
                "Открытых ошибок справочников нет"
                if master_issues == 0
                else f"Открытых ошибок справочников: {master_issues}"
            ),
            "integrations",
            value=master_issues,
        )
    )

    rates = int(counts["payroll_rates"] or 0)
    checks.append(
        _check(
            "payroll_rates",
            "Сдельные тарифы",
            "READY" if rates > 0 else "BLOCKED",
            (
                f"Действующих тарифных правил: {rates}"
                if rates
                else "Тарифная сетка не загружена"
            ),
            "payroll",
            scope="PAYROLL",
            value=rates,
        )
    )

    payroll_coverage = _coverage(
        payroll_confirmed,
        active_products,
    )
    payroll_status = (
        "READY"
        if active_products > 0 and payroll_confirmed >= active_products
        else (
            "WARNING"
            if payroll_confirmed > 0
            else "BLOCKED"
        )
    )
    checks.append(
        _check(
            "payroll_product_attributes",
            "Тарифные признаки номенклатуры",
            payroll_status,
            (
                f"Подтверждено {payroll_confirmed} из {active_products} "
                f"({payroll_coverage or 0}%)"
            ),
            "payroll",
            scope="PAYROLL",
            value=payroll_coverage,
        )
    )

    economist_users = roles.get(
        "ECONOMIST",
        {"active_users": 0},
    )["active_users"]
    checks.append(
        _check(
            "economist_user",
            "Экономист для расчета ЗП",
            "READY" if economist_users > 0 else "BLOCKED",
            (
                f"Активных пользователей: {economist_users}"
                if economist_users
                else "Не назначен пользователь с ролью Экономист"
            ),
            "users",
            scope="PAYROLL",
            value=economist_users,
        )
    )

    core_checks = [item for item in checks if item["scope"] == "CORE"]
    payroll_checks = [
        item for item in checks if item["scope"] == "PAYROLL"
    ]

    core_blockers = sum(
        1 for item in core_checks if item["status"] == "BLOCKED"
    )
    payroll_blockers = sum(
        1 for item in payroll_checks if item["status"] == "BLOCKED"
    )

    return {
        "summary": {
            "production_ready": core_blockers == 0,
            "production_blockers": core_blockers,
            "production_warnings": sum(
                1 for item in core_checks if item["status"] == "WARNING"
            ),
            "payroll_ready": payroll_blockers == 0,
            "payroll_blockers": payroll_blockers,
            "payroll_warnings": sum(
                1 for item in payroll_checks if item["status"] == "WARNING"
            ),
        },
        "counts": {
            **{key: int(value or 0) for key, value in dict(counts).items()},
            "erp_plan_rows": int(plan_rows["total"] or 0),
            "erp_runs_created": int(plan_rows["runs_created"] or 0),
            "erp_plan_unresolved": int(plan_rows["unresolved"] or 0),
        },
        "roles": roles,
        "checks": checks,
    }
