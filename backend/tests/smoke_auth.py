from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import hash_password
from app.database import engine
from app.main import app
from app.norm_admin_service import save_manual_norm
from app.production_manager_service import verify_shift
from app.reconciliation_service import save_reconciliation_case, shift_reconciliation
from app.shift_master_service import close_shift, complete_production_run
from app.workspace_service import (
    record_accounting_control,
    record_operator_output,
    record_qc_defect,
    record_warehouse_receipt,
)
from app.shifts import ensure_shift


ADMIN_EMAIL = "ci-admin@example.com"
ADMIN_PASSWORD = "AdminSmokePass123!"
OPERATOR_EMAIL = "ci-operator@example.com"
OPERATOR_PASSWORD = "OperatorSmokePass123!"


def _create_user(email: str, password: str, role_code: str) -> None:
    with engine.begin() as connection:
        role_id = connection.execute(
            text("SELECT id FROM roles WHERE code = :code"),
            {"code": role_code},
        ).scalar_one()

        user_id = connection.execute(
            text(
                """
                INSERT INTO users (
                    email,
                    password_hash,
                    is_active,
                    must_change_password,
                    password_changed_at
                ) VALUES (
                    :email,
                    :password_hash,
                    true,
                    false,
                    now()
                )
                ON CONFLICT (email)
                DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    is_active = true,
                    must_change_password = false,
                    failed_login_attempts = 0,
                    locked_until = NULL,
                    updated_at = now()
                RETURNING id
                """
            ),
            {
                "email": email,
                "password_hash": hash_password(password),
            },
        ).scalar_one()

        connection.execute(
            text("DELETE FROM user_roles WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (:user_id, :role_id)
                """
            ),
            {"user_id": user_id, "role_id": role_id},
        )


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    return body["access_token"]


def _test_shift_rules() -> None:
    business_date = date(2026, 9, 24)

    with engine.begin() as connection:
        day_id = ensure_shift(connection, business_date, "DAY")
        night_id = ensure_shift(connection, business_date, "NIGHT")

        rows = connection.execute(
            text(
                """
                SELECT
                    s.id,
                    st.code,
                    s.business_date,
                    s.started_at,
                    s.ended_at
                FROM shifts s
                JOIN shift_types st ON st.id = s.shift_type_id
                WHERE s.id IN (:day_id, :night_id)
                ORDER BY st.code
                """
            ),
            {"day_id": day_id, "night_id": night_id},
        ).mappings().all()

    by_code = {row["code"]: row for row in rows}
    assert set(by_code) == {"DAY", "NIGHT"}

    tz = ZoneInfo("Europe/Moscow")

    day = by_code["DAY"]
    day_start = day["started_at"].astimezone(tz)
    day_end = day["ended_at"].astimezone(tz)
    assert day["business_date"] == business_date
    assert day_start.date() == business_date
    assert day_start.timetz().replace(tzinfo=None) == time(9, 0)
    assert day_end.date() == business_date
    assert day_end.timetz().replace(tzinfo=None) == time(21, 0)

    night = by_code["NIGHT"]
    night_start = night["started_at"].astimezone(tz)
    night_end = night["ended_at"].astimezone(tz)
    assert night["business_date"] == business_date
    assert night_start.date() == business_date
    assert night_start.timetz().replace(tzinfo=None) == time(21, 0)
    assert night_end.date() == date(2026, 9, 25)
    assert night_end.timetz().replace(tzinfo=None) == time(9, 0)


def _test_manual_norm() -> None:
    business_date = date(2026, 9, 24)

    with engine.begin() as connection:
        admin_id = connection.execute(
            text("SELECT id FROM users WHERE email=:email"),
            {"email": ADMIN_EMAIL},
        ).scalar_one()

        product_id = connection.execute(
            text(
                """
                INSERT INTO products (code, article, name, unit, is_active)
                VALUES ('CI-NORM-PRODUCT','CI-NORM-PRODUCT','CI Norm Product','pcs',true)
                ON CONFLICT (code)
                DO UPDATE SET is_active=true
                RETURNING id
                """
            )
        ).scalar_one()

        equipment_id = connection.execute(
            text(
                """
                INSERT INTO equipment (code, name, is_active)
                VALUES ('CI-NORM-LINE','CI Norm Line',true)
                ON CONFLICT (code)
                DO UPDATE SET is_active=true
                RETURNING id
                """
            )
        ).scalar_one()

        shift_id = ensure_shift(connection, business_date, "DAY")

        run_id = connection.execute(
            text(
                """
                INSERT INTO production_runs (
                    shift_id,
                    equipment_id,
                    product_id,
                    planned_qty,
                    ideal_rate_per_hour,
                    status
                ) VALUES (
                    :shift_id,
                    :equipment_id,
                    :product_id,
                    1000,
                    NULL,
                    'PLANNED'
                )
                RETURNING id
                """
            ),
            {
                "shift_id": shift_id,
                "equipment_id": equipment_id,
                "product_id": product_id,
            },
        ).scalar_one()

    saved = save_manual_norm(
        norm_id=None,
        product_id=product_id,
        equipment_id=equipment_id,
        ideal_rate_per_hour=Decimal("5000"),
        valid_from=business_date,
        valid_to=None,
        apply_to_open_runs=True,
        user_id=admin_id,
    )
    assert saved["ideal_rate_per_hour"] == 5000.0
    assert saved["applied_runs"] >= 1

    with engine.begin() as connection:
        rate = connection.execute(
            text(
                """
                SELECT ideal_rate_per_hour
                FROM production_runs
                WHERE id=:run_id
                """
            ),
            {"run_id": run_id},
        ).scalar_one()
    assert float(rate) == 5000.0

    overlap_blocked = False
    try:
        save_manual_norm(
            norm_id=None,
            product_id=product_id,
            equipment_id=equipment_id,
            ideal_rate_per_hour=Decimal("5100"),
            valid_from=business_date,
            valid_to=None,
            apply_to_open_runs=False,
            user_id=admin_id,
        )
    except ValueError:
        overlap_blocked = True
    assert overlap_blocked, "overlapping production norm was not blocked"


def _test_full_shift_lifecycle() -> None:
    business_date = date(2026, 9, 20)
    shift_code = "DAY"

    with engine.begin() as connection:
        admin_id = connection.execute(
            text("SELECT id FROM users WHERE email=:email"),
            {"email": ADMIN_EMAIL},
        ).scalar_one()

        product_id = connection.execute(
            text(
                """
                INSERT INTO products (code, article, name, unit, is_active)
                VALUES ('CI-LIFE-PRODUCT','CI-LIFE-PRODUCT','CI Lifecycle Product','pcs',true)
                ON CONFLICT (code)
                DO UPDATE SET is_active=true
                RETURNING id
                """
            )
        ).scalar_one()

        equipment_id = connection.execute(
            text(
                """
                INSERT INTO equipment (code, name, is_active)
                VALUES ('CI-LIFE-LINE','CI Lifecycle Line',true)
                ON CONFLICT (code)
                DO UPDATE SET is_active=true
                RETURNING id
                """
            )
        ).scalar_one()

        defect_reason_id = connection.execute(
            text(
                """
                INSERT INTO defect_reasons (code, category, name, is_active)
                VALUES ('CI-QC','QUALITY','CI QC defect',true)
                ON CONFLICT (code)
                DO UPDATE SET is_active=true
                RETURNING id
                """
            )
        ).scalar_one()

        shift_id = ensure_shift(connection, business_date, shift_code)

        order_id = connection.execute(
            text(
                """
                INSERT INTO production_orders (
                    order_no,
                    product_id,
                    planned_quantity,
                    status
                ) VALUES (
                    'CI-LIFE-ORDER',
                    :product_id,
                    1000,
                    'PLANNED'
                )
                ON CONFLICT (order_no, product_id)
                DO UPDATE SET planned_quantity=1000, status='PLANNED'
                RETURNING id
                """
            ),
            {"product_id": product_id},
        ).scalar_one()

        run_id = connection.execute(
            text(
                """
                INSERT INTO production_runs (
                    shift_id,
                    equipment_id,
                    product_id,
                    production_order_id,
                    planned_qty,
                    ideal_rate_per_hour,
                    status
                ) VALUES (
                    :shift_id,
                    :equipment_id,
                    :product_id,
                    :order_id,
                    1000,
                    5000,
                    'PLANNED'
                )
                RETURNING id
                """
            ),
            {
                "shift_id": shift_id,
                "equipment_id": equipment_id,
                "product_id": product_id,
                "order_id": order_id,
            },
        ).scalar_one()

        shift_times = connection.execute(
            text(
                """
                SELECT started_at, ended_at
                FROM shifts
                WHERE id=:shift_id
                """
            ),
            {"shift_id": shift_id},
        ).mappings().one()

    user = {"id": str(admin_id)}
    t1 = shift_times["started_at"] + timedelta(hours=1)
    t2 = shift_times["started_at"] + timedelta(hours=2)
    t3 = shift_times["started_at"] + timedelta(hours=3)
    t4 = shift_times["started_at"] + timedelta(hours=4)

    record_operator_output(
        user,
        run_id,
        Decimal("1000"),
        Decimal("0"),
        t1,
        "CI lifecycle output",
        "ci-life-output",
    )

    record_qc_defect(
        user,
        run_id,
        Decimal("20"),
        defect_reason_id,
        t2,
        "CI lifecycle QC",
        "ci-life-qc",
    )

    record_accounting_control(
        user,
        run_id,
        Decimal("98"),
        Decimal("10"),
        t3,
        "CI-TICKET",
        "CI lifecycle accounting",
        "ci-life-accounting",
    )

    record_warehouse_receipt(
        user,
        run_id,
        Decimal("980"),
        t4,
        "CI-WH",
        "ci-life-warehouse",
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO erp_production_facts (
                    erp_document_id,
                    erp_document_no,
                    production_order_id,
                    product_id,
                    production_run_id,
                    occurred_at,
                    quantity,
                    defect_quantity
                ) VALUES (
                    'CI-LIFE-ERP',
                    'CI-LIFE-ERP',
                    :order_id,
                    :product_id,
                    :run_id,
                    :occurred_at,
                    980,
                    20
                )
                """
            ),
            {
                "order_id": order_id,
                "product_id": product_id,
                "run_id": run_id,
                "occurred_at": t4,
            },
        )

    reconciliation = shift_reconciliation(business_date, shift_code)
    row = next(
        item for item in reconciliation["rows"]
        if item["production_run_id"] == str(run_id)
    )
    assert row["severity"] in {"WARNING", "CRITICAL"}
    assert row["delta_qc_accountant"] == 0
    assert row["delta_accountant_warehouse"] == 0
    assert row["delta_warehouse_erp"] == 0

    save_reconciliation_case(
        production_run_id=run_id,
        status="RESOLVED",
        reason_code="QC_DIFFERENCE",
        comment="CI lifecycle: confirmed QC defect explains operator/QC delta",
        user_id=admin_id,
    )

    completed = complete_production_run(run_id, admin_id)
    assert completed["status"] == "COMPLETED"

    closed = close_shift(business_date, shift_code, admin_id)
    assert closed["status"] == "CLOSED"

    verified = verify_shift(business_date, shift_code, admin_id)
    assert verified["status"] == "VERIFIED"

    with engine.begin() as connection:
        final_shift_status = connection.execute(
            text("SELECT status FROM shifts WHERE id=:id"),
            {"id": shift_id},
        ).scalar_one()
        final_run_status = connection.execute(
            text("SELECT status FROM production_runs WHERE id=:id"),
            {"id": run_id},
        ).scalar_one()

    assert final_shift_status == "VERIFIED"
    assert final_run_status == "VERIFIED"


def main() -> None:
    _create_user(ADMIN_EMAIL, ADMIN_PASSWORD, "ADMIN")
    _create_user(OPERATOR_EMAIL, OPERATOR_PASSWORD, "OPERATOR")
    _test_shift_rules()
    _test_manual_norm()
    _test_full_shift_lifecycle()

    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200, health.text
    health_body = health.json()
    assert health_body["status"] == "ok"
    assert health_body["database"] == "ok"
    assert health_body["schema_version"] == "012_reconciliation_cases.sql"

    unauthenticated = client.get("/api/v1/admin/users/meta")
    assert unauthenticated.status_code == 401

    admin_token = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    me = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200, me.text
    assert "ADMIN" in me.json()["roles"]

    admin_meta = client.get(
        "/api/v1/admin/users/meta",
        headers=admin_headers,
    )
    assert admin_meta.status_code == 200, admin_meta.text
    assert any(
        role["code"] == "ADMIN"
        for role in admin_meta.json()["roles"]
    )

    operator_token = _login(
        client,
        OPERATOR_EMAIL,
        OPERATOR_PASSWORD,
    )
    operator_headers = {
        "Authorization": f"Bearer {operator_token}"
    }

    operator_me = client.get(
        "/api/v1/auth/me",
        headers=operator_headers,
    )
    assert operator_me.status_code == 200
    assert operator_me.json()["roles"] == ["OPERATOR"]

    forbidden = client.get(
        "/api/v1/admin/users/meta",
        headers=operator_headers,
    )
    assert forbidden.status_code == 403

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={
            "email": OPERATOR_EMAIL,
            "password": "WrongPassword123!",
        },
    )
    assert wrong_password.status_code == 401

    print("smoke test ok")


if __name__ == "__main__":
    main()
