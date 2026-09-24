from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import psycopg

from .config import settings


MIGRATION_LOCK_ID = 864217530


def _dsn() -> str:
    value = settings.database_url
    if value.startswith("postgresql+psycopg://"):
        return "postgresql://" + value[len("postgresql+psycopg://"):]
    return value


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _migration_files(path: Path) -> list[Path]:
    files = sorted(
        file
        for file in path.glob("*.sql")
        if file.is_file() and file.name[:3].isdigit()
    )
    if not files:
        raise RuntimeError(f"No SQL migrations found in {path}")
    return files


def run_migrations(path: Path) -> dict:
    files = _migration_files(path)
    applied = []
    skipped = []

    with psycopg.connect(_dsn()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        connection.commit()

        connection.execute(
            "SELECT pg_advisory_lock(%s)",
            (MIGRATION_LOCK_ID,),
        )

        try:
            for file in files:
                version = file.name
                content = file.read_bytes()
                checksum = _checksum(content)

                current = connection.execute(
                    """
                    SELECT checksum
                    FROM schema_migrations
                    WHERE version = %s
                    """,
                    (version,),
                ).fetchone()

                if current:
                    if current[0] != checksum:
                        raise RuntimeError(
                            f"Migration {version} was changed after it was applied"
                        )
                    skipped.append(version)
                    continue

                sql = content.decode("utf-8")
                try:
                    with connection.transaction():
                        with connection.cursor() as cursor:
                            cursor.execute(sql, prepare=False)
                        connection.execute(
                            """
                            INSERT INTO schema_migrations (
                                version,
                                checksum
                            ) VALUES (%s, %s)
                            """,
                            (version, checksum),
                        )
                except Exception as exc:
                    raise RuntimeError(
                        f"Migration {version} failed: {exc}"
                    ) from exc

                applied.append(version)
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (MIGRATION_LOCK_ID,),
            )
            connection.commit()

    return {
        "applied": applied,
        "skipped": skipped,
        "latest": files[-1].name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply VITAGROUP SQL migrations in order"
    )
    parser.add_argument(
        "--path",
        default="/migrations",
        help="Directory containing numbered SQL migration files",
    )
    args = parser.parse_args()

    result = run_migrations(Path(args.path))
    print(
        "Migrations complete. "
        f"Applied: {len(result['applied'])}; "
        f"Skipped: {len(result['skipped'])}; "
        f"Latest: {result['latest']}"
    )


if __name__ == "__main__":
    main()
