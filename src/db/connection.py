"""DB connection + migrations. Postgres 16 per AGENTS.md §8.

DATABASE_URL env var, e.g. postgresql://bot:bot@localhost:5432/tennis
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return url


@contextmanager
def connect(url: str | None = None):
    """Yield a psycopg connection with dict rows; commits on success."""
    conn = psycopg.connect(url or database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(url: str | None = None) -> list[str]:
    """Apply schema.sql then migrations/*.sql in order. Idempotent.

    Returns list of newly applied migration names.
    """
    applied: list[str] = []
    with connect(url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "  name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM _migrations")}

        # baseline schema first (only once — schema.sql has no IF NOT EXISTS,
        # so guard on whether core tables already exist)
        exists = conn.execute(
            "SELECT to_regclass('public.decisions') AS t"
        ).fetchone()["t"]
        if not exists:
            conn.execute(SCHEMA_PATH.read_text())
            conn.execute(
                "INSERT INTO _migrations (name) VALUES ('schema.sql') "
                "ON CONFLICT DO NOTHING"
            )
            applied.append("schema.sql")

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done or path.name == "README.md":
                continue
            conn.execute(path.read_text())
            conn.execute(
                "INSERT INTO _migrations (name) VALUES (%s)", (path.name,)
            )
            applied.append(path.name)
    return applied
