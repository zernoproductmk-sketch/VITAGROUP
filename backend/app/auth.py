from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import text

from .config import settings
from .database import engine


password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Пароль должен содержать не менее 12 символов")
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hash.verify(password, stored_hash)
    except Exception:
        return False


def create_access_token(user_id: UUID, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(
            (
                now
                + timedelta(minutes=settings.auth_access_token_minutes)
            ).timestamp()
        ),
        "iss": "vitagroup-oee",
        "aud": "vitagroup-web",
    }
    return jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm="HS256",
    )


def _user_payload(connection, user_id: UUID) -> dict | None:
    row = connection.execute(
        text(
            """
            SELECT
                u.id,
                u.email,
                u.employee_id,
                u.is_active,
                u.must_change_password,
                u.last_login_at,
                e.personnel_number,
                e.full_name,
                e.position_name,
                e.department_name
            FROM users u
            LEFT JOIN employees e ON e.id = u.employee_id
            WHERE u.id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if not row:
        return None

    roles = [
        item["code"]
        for item in connection.execute(
            text(
                """
                SELECT r.code
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
                ORDER BY r.code
                """
            ),
            {"user_id": user_id},
        ).mappings()
    ]

    return {
        **dict(row),
        "id": str(row["id"]),
        "employee_id": (
            str(row["employee_id"]) if row["employee_id"] else None
        ),
        "roles": roles,
    }


def authenticate(
    email: str,
    password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                SELECT *
                FROM users
                WHERE lower(email) = :email
                FOR UPDATE
                """
            ),
            {"email": normalized_email},
        ).mappings().first()

        if not row:
            connection.execute(
                text(
                    """
                    INSERT INTO auth_login_events (
                        email, success, reason, ip_address, user_agent
                    ) VALUES (
                        :email, false, 'USER_NOT_FOUND',
                        CAST(:ip_address AS inet), :user_agent
                    )
                    """
                ),
                {
                    "email": normalized_email,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль",
            )

        if not row["is_active"]:
            connection.execute(
                text(
                    """
                    INSERT INTO auth_login_events (
                        user_id, email, success, reason, ip_address, user_agent
                    ) VALUES (
                        :user_id, :email, false, 'INACTIVE',
                        CAST(:ip_address AS inet), :user_agent
                    )
                    """
                ),
                {
                    "user_id": row["id"],
                    "email": normalized_email,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись отключена",
            )

        if row["locked_until"] and row["locked_until"] > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток входа. Повторите позже.",
            )

        if not verify_password(password, row["password_hash"]):
            attempts = int(row["failed_login_attempts"] or 0) + 1
            locked_until = (
                now + timedelta(minutes=settings.auth_lock_minutes)
                if attempts >= settings.auth_max_failed_attempts
                else None
            )
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET failed_login_attempts = :attempts,
                        locked_until = :locked_until,
                        updated_at = now()
                    WHERE id = :user_id
                    """
                ),
                {
                    "attempts": attempts,
                    "locked_until": locked_until,
                    "user_id": row["id"],
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO auth_login_events (
                        user_id, email, success, reason, ip_address, user_agent
                    ) VALUES (
                        :user_id, :email, false, 'BAD_PASSWORD',
                        CAST(:ip_address AS inet), :user_agent
                    )
                    """
                ),
                {
                    "user_id": row["id"],
                    "email": normalized_email,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль",
            )

        connection.execute(
            text(
                """
                UPDATE users
                SET failed_login_attempts = 0,
                    locked_until = NULL,
                    last_login_at = now(),
                    updated_at = now()
                WHERE id = :user_id
                """
            ),
            {"user_id": row["id"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO auth_login_events (
                    user_id, email, success, reason, ip_address, user_agent
                ) VALUES (
                    :user_id, :email, true, 'LOGIN',
                    CAST(:ip_address AS inet), :user_agent
                )
                """
            ),
            {
                "user_id": row["id"],
                "email": normalized_email,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )

        user = _user_payload(connection, row["id"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Учетная запись не найдена",
        )
    return user


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            audience="vitagroup-web",
            issuer="vitagroup-oee",
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительная сессия",
        ) from exc


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительная сессия",
        )

    with engine.begin() as connection:
        user = _user_payload(connection, UUID(user_id))

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Учетная запись недоступна",
        )
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    def dependency(user: CurrentUser) -> dict:
        if not allowed.intersection(user["roles"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user

    return dependency


def change_password(
    user_id: UUID,
    current_password: str,
    new_password: str,
) -> None:
    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                SELECT password_hash
                FROM users
                WHERE id = :user_id
                FOR UPDATE
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        if not row or not verify_password(
            current_password,
            row["password_hash"],
        ):
            raise ValueError("Текущий пароль указан неверно")

        new_hash = hash_password(new_password)
        connection.execute(
            text(
                """
                UPDATE users
                SET password_hash = :password_hash,
                    must_change_password = false,
                    password_changed_at = now(),
                    updated_at = now()
                WHERE id = :user_id
                """
            ),
            {
                "password_hash": new_hash,
                "user_id": user_id,
            },
        )
