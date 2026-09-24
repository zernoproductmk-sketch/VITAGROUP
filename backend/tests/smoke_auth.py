from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import hash_password
from app.database import engine
from app.main import app
from app.shifts import ensure_shift


ADMIN_EMAIL = "ci-admin@vitagroup.local"
ADMIN_PASSWORD = "AdminSmokePass123!"
OPERATOR_EMAIL = "ci-operator@vitagroup.local"
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


def main() -> None:
    _create_user(ADMIN_EMAIL, ADMIN_PASSWORD, "ADMIN")
    _create_user(OPERATOR_EMAIL, OPERATOR_PASSWORD, "OPERATOR")
    _test_shift_rules()

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
