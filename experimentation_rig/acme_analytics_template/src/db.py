"""Database access. The database location comes from the DATABASE_PATH environment variable."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def database_path() -> str:
    configured = os.environ.get("DATABASE_PATH")
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2] / "data" / "acme.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
