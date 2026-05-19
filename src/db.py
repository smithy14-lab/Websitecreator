"""DB connection abstraction. SQLite for local dev, Postgres for production.

Selection is driven by the DATABASE_URL env var. If unset → SQLite file in repo root.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

SQLITE_PATH = Path(__file__).parent.parent / "leads.db"

if IS_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


@contextmanager
def get_conn():
    if IS_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def q(sql: str) -> str:
    """Convert SQLite-style ? placeholders to %s for Postgres."""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


def row_to_dict(row) -> dict:
    """Normalize a row to a plain dict regardless of driver."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def autoincrement_pk() -> str:
    """Return the right PK type for the active driver."""
    return "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
