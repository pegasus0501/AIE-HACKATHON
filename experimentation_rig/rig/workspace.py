"""What an agent may see and write. Nothing under rig/ or the answer key is ever returned."""
from __future__ import annotations

import sqlite3
from pathlib import PurePosixPath

from . import common
from .snapshot import path_for

WRITABLE = {
    "engineer": ("migrations/", "queries/", "src/"),
    "tester": ("tests/",),
}
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".db"}


def check_role(role: str) -> str:
    if role not in WRITABLE:
        raise ValueError(f"unknown role {role!r}; expected one of {sorted(WRITABLE)}")
    return role


def validate_paths(files: dict, role: str) -> None:
    """Raise ValueError unless every path is relative, has no '..' and sits under the role's allowlist."""
    check_role(role)
    for name in files:
        if not isinstance(name, str) or not name:
            raise ValueError(f"invalid path {name!r}")
        norm = name.replace("\\", "/")
        pure = PurePosixPath(norm)
        if pure.is_absolute() or norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
            raise ValueError(f"absolute path rejected: {name}")
        if ".." in pure.parts:
            raise ValueError(f"path with '..' rejected: {name}")
        if not any(str(pure).startswith(prefix) for prefix in WRITABLE[role]):
            raise ValueError(f"{role} may not write {name}; allowed: {', '.join(WRITABLE[role])}")


def read_tree(base) -> dict:
    """Read every text file under base into {posix_relative_path: text}."""
    out: dict = {}
    base = common.Path(base)
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if any(part in SKIP_DIRS for part in rel.parts) or path.suffix in SKIP_SUFFIXES:
            continue
        try:
            out[rel.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return out


def build(ticket_id: str, role: str) -> dict:
    """Files the role may see: the repository, the ticket and the approved contract."""
    common.check_ticket(ticket_id)
    check_role(role)
    files = read_tree(common.TEMPLATE_DIR)
    files["TICKET.md"] = (common.TICKETS_DIR / f"{ticket_id}.md").read_text(encoding="utf-8")
    files["CONTRACT.md"] = (common.CONTRACTS_DIR / f"{ticket_id}.md").read_text(encoding="utf-8")
    return files


def schema_text(ticket_id: str) -> str:
    """Schema dump of the ticket's snapshot, for use in prompts."""
    conn = common.connect_ro(path_for(ticket_id))
    try:
        order = {"table": 0, "index": 1, "view": 2, "trigger": 3}
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        conn.close()
    rows.sort(key=lambda r: (order.get(r[0], 9), r[1]))
    return "\n\n".join(r[2].strip() + ";" for r in rows) + "\n"
