"""Minimal migration runner.

Usage (from the repository root):
    python -m src.migrate status
    python -m src.migrate up
    python -m src.migrate down [steps]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .db import database_path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
_NAME = re.compile(r"^(\d{3})_(.+)\.(up|down)\.sql$")


def discover(directory: Path = MIGRATIONS_DIR) -> dict:
    found: dict = {}
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if match:
            version, name, direction = match.groups()
            found.setdefault(version, {"name": name})[direction] = path
    return found


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> list:
    ensure_table(conn)
    return [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def _run_script(conn: sqlite3.Connection, sql: str, bookkeeping: str, params: tuple) -> None:
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("BEGIN;\n" + sql + "\n;")
        conn.execute(bookkeeping, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def up(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list:
    done = set(applied_versions(conn))
    ran = []
    for version, parts in discover(directory).items():
        if version in done:
            continue
        if "up" not in parts:
            raise RuntimeError(f"migration {version} has no up script")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _run_script(conn, parts["up"].read_text(encoding="utf-8"),
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, parts["name"], now))
        ran.append(version)
    return ran


def down(conn: sqlite3.Connection, steps: int = 1, directory: Path = MIGRATIONS_DIR) -> list:
    found = discover(directory)
    rolled = []
    for version in reversed(applied_versions(conn)[-steps:]):
        parts = found.get(version, {})
        if "down" not in parts:
            raise RuntimeError(f"migration {version} has no down script")
        _run_script(conn, parts["down"].read_text(encoding="utf-8"),
                    "DELETE FROM schema_migrations WHERE version = ?", (version,))
        rolled.append(version)
    return rolled


def main(argv: list) -> int:
    command = argv[0] if argv else "status"
    conn = sqlite3.connect(database_path())
    try:
        if command == "status":
            print("applied:", ", ".join(applied_versions(conn)) or "(none)")
        elif command == "up":
            print("applied now:", ", ".join(up(conn)) or "(nothing to do)")
        elif command == "down":
            steps = int(argv[1]) if len(argv) > 1 else 1
            print("rolled back:", ", ".join(down(conn, steps)) or "(nothing to do)")
        else:
            print(f"unknown command: {command}")
            return 2
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
