from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from .auth import hash_password
from .database import engine


def list_users() -> list[dict]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    u.id,
                    u.email,
                    u.employee_id,
                    u.is_active,
                    u.must_change_password,
                    u.last_login_at,
                    u.created_at,
                    e.personnel_number,
                    e.full_name,
                    e.position_name,
                    e.department_name,
                    COALESCE(
                        array_agg(r.code ORDER BY r.code)
                        FILTER (WHERE r.code IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS roles
                FROM users u
                LEFT JOIN employees e ON e.id = u.employee_id
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                GROUP BY u.id, e.id
                ORDER BY u.email
                """
            )
        ).mappings().all()
    return [
        {
            **dict(row),
            "id": str(row["id"]),
            "employee_id": (
                str(row["employee_id"]) if row["employee_id"] else None
            ),
        }
        for row in rows
    ]


def create_user(
    email: str,
    password: str,
    roles: list[str],
    employee_id: UUID | None = None,
) -> dict:
    normalized_email = email.strip().lower()
    password_value = hash_password(password)

    with engine.begin() as connection:
        available = {
            row["code"]
            for row in connection.execute(
                text("SELECT code FROM roles")
            ).mappings()
        }
        unknown = sorted(set(roles) - available)
        if unknown:
            raise ValueError(
                f"Неизвестные роли: {', '.join(unknown)}"
            )

        user_id = connection.execute(
            text(
                """
                INSERT INTO users (
                    email,
                    password_hash,
                    employee_id,
                    is_active,
                    must_change_password
                ) VALUES (
                    :email,
                    :password_hash,
                    :employee_id,
                    true,
                    true
                )
                RETURNING id
                """
            ),
            {
                "email": normalized_email,
                "password_hash": password_value,
                "employee_id": employee_id,
            },
        ).scalar_one()

        for role_code in sorted(set(roles)):
            connection.execute(
                text(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    SELECT :user_id, id
                    FROM roles
                    WHERE code = :role_code
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "user_id": user_id,
                    "role_code": role_code,
                },
            )

        row = connection.execute(
            text(
                """
                SELECT email, is_active, must_change_password
                FROM users
                WHERE id = :id
                """
            ),
            {"id": user_id},
        ).mappings().one()

    return {
        "id": str(user_id),
        **dict(row),
        "roles": sorted(set(roles)),
        "employee_id": str(employee_id) if employee_id else None,
    }


def set_user_roles(user_id: UUID, roles: list[str]) -> dict:
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar_one_or_none()
        if not exists:
            raise LookupError("Пользователь не найден")

        available = {
            row["code"]
            for row in connection.execute(
                text("SELECT code FROM roles")
            ).mappings()
        }
        unknown = sorted(set(roles) - available)
        if unknown:
            raise ValueError(
                f"Неизвестные роли: {', '.join(unknown)}"
            )

        connection.execute(
            text("DELETE FROM user_roles WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        for role_code in sorted(set(roles)):
            connection.execute(
                text(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    SELECT :user_id, id
                    FROM roles
                    WHERE code = :role_code
                    """
                ),
                {"user_id": user_id, "role_code": role_code},
            )

    return {
        "status": "ok",
        "user_id": str(user_id),
        "roles": sorted(set(roles)),
    }


def set_user_active(user_id: UUID, is_active: bool) -> dict:
    with engine.begin() as connection:
        updated = connection.execute(
            text(
                """
                UPDATE users
                SET is_active = :is_active,
                    updated_at = now()
                WHERE id = :id
                RETURNING id
                """
            ),
            {"id": user_id, "is_active": is_active},
        ).scalar_one_or_none()
        if not updated:
            raise LookupError("Пользователь не найден")

    return {
        "status": "ok",
        "user_id": str(user_id),
        "is_active": is_active,
    }


def list_admin_meta() -> dict:
    with engine.begin() as connection:
        roles = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT code, name
                    FROM roles
                    ORDER BY name
                    """
                )
            ).mappings()
        ]

        employees = [
            {
                **dict(row),
                "id": str(row["id"]),
            }
            for row in connection.execute(
                text(
                    """
                    SELECT
                        e.id,
                        e.personnel_number,
                        e.full_name,
                        e.position_name,
                        e.department_name,
                        u.id AS user_id
                    FROM employees e
                    LEFT JOIN users u ON u.employee_id = e.id
                    WHERE e.is_active = true
                    ORDER BY e.full_name
                    """
                )
            ).mappings()
        ]

    return {
        "roles": roles,
        "employees": employees,
    }


def reset_user_password(user_id: UUID, new_password: str) -> dict:
    password_value = hash_password(new_password)
    with engine.begin() as connection:
        updated = connection.execute(
            text(
                """
                UPDATE users
                SET password_hash = :password_hash,
                    must_change_password = true,
                    failed_login_attempts = 0,
                    locked_until = NULL,
                    password_changed_at = now(),
                    updated_at = now()
                WHERE id = :id
                RETURNING id
                """
            ),
            {
                "id": user_id,
                "password_hash": password_value,
            },
        ).scalar_one_or_none()

        if not updated:
            raise LookupError("Пользователь не найден")

    return {
        "status": "ok",
        "user_id": str(user_id),
        "must_change_password": True,
    }
