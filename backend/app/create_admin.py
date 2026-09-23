from __future__ import annotations

import argparse
import getpass
import os

from sqlalchemy import text

from .auth import hash_password
from .database import engine


def main():
    parser = argparse.ArgumentParser(
        description="Create or reset the initial VITAGROUP administrator."
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = os.getenv("VITAGROUP_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Initial administrator password: ")

    password_value = hash_password(password)
    email = args.email.strip().lower()

    with engine.begin() as connection:
        role_id = connection.execute(
            text("SELECT id FROM roles WHERE code = 'ADMIN'")
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
                    true,
                    now()
                )
                ON CONFLICT (email)
                DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    is_active = true,
                    must_change_password = true,
                    failed_login_attempts = 0,
                    locked_until = NULL,
                    password_changed_at = now(),
                    updated_at = now()
                RETURNING id
                """
            ),
            {
                "email": email,
                "password_hash": password_value,
            },
        ).scalar_one()

        connection.execute(
            text(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (:user_id, :role_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": user_id, "role_id": role_id},
        )

    print(f"Administrator ready: {email}")


if __name__ == "__main__":
    main()
