"""SQLite access layer with versioned migrations.

* Every call opens a short-lived connection (safe across Streamlit threads and job workers).
* `transaction()` wraps several statements atomically.
* Migrations are plain SQL files in `lucerna/migrations/NNNN_name.sql`, applied once, in order,
  and recorded in `schema_migrations`.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path or settings().db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return con


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        con.execute("BEGIN")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]
    finally:
        con.close()


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Execute one statement; returns lastrowid."""
    con = connect()
    try:
        cur = con.execute(sql, tuple(params))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def now() -> float:
    return time.time()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def applied_migrations() -> list[str]:
    con = connect()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at REAL)")
        return [r[0] for r in con.execute("SELECT version FROM schema_migrations ORDER BY version")]
    finally:
        con.close()


def migrate() -> list[str]:
    """Apply pending migrations. Returns the list of versions applied now."""
    done = set(applied_migrations())
    newly: list[str] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem
        if version in done:
            continue
        sql = f.read_text(encoding="utf-8")
        con = connect()
        try:
            con.execute("PRAGMA foreign_keys=OFF")
            con.executescript("BEGIN;\n" + sql + "\nINSERT INTO schema_migrations(version, applied_at) VALUES('"
                              + version.replace("'", "") + f"', {time.time()});\nCOMMIT;")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            con.close()
        newly.append(version)
    return newly


_initialised: set[str] = set()


def init() -> None:
    """Idempotent: migrate the configured database once per process."""
    key = str(settings().db_path)
    if key in _initialised:
        return
    migrate()
    from .services import bootstrap  # local import to avoid cycles
    bootstrap.seed_defaults()
    _initialised.add(key)


def reset_init_cache() -> None:
    _initialised.clear()
