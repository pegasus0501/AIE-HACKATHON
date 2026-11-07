"""Shared paths and helpers. Every path is derived from this file's location."""
from __future__ import annotations

import os
import shutil
import stat
import sqlite3
from pathlib import Path

RIG_DIR = Path(__file__).resolve().parent
ROOT = RIG_DIR.parent  # experimentation_rig/
DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
WORK_DIR = DATA_DIR / "work"
ACME_DB = DATA_DIR / "acme.db"
TRUTH_DB = DATA_DIR / "truth.db"
TEMPLATE_DIR = ROOT / "acme_analytics_template"
REPO_DIR = ROOT / "acme_analytics"
TICKETS_DIR = RIG_DIR / "tickets"
CONTRACTS_DIR = RIG_DIR / "contracts"
KEY_DIR = RIG_DIR / "answer_key"
REFERENCE_DIR = RIG_DIR / "reference"
MUTANTS_DIR = RIG_DIR / "mutants"
TICKETS = ("exp1", "exp2", "exp3")


def _load_env_file() -> dict:
    out: dict = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


_ENV = _load_env_file()


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or _ENV.get(name) or default


SEED = int(setting("SEED", "42"))
AS_OF = setting("AS_OF", "2025-06-30")
QUERY_MAX_ROWS = int(setting("QUERY_MAX_ROWS", "200"))
QUERY_TIMEOUT = float(setting("QUERY_TIMEOUT_SECONDS", "5"))
RUN_TIMEOUT = int(setting("RUN_TIMEOUT_SECONDS", "300"))


def check_ticket(ticket: str) -> str:
    if ticket not in TICKETS:
        raise ValueError(f"unknown ticket {ticket!r}; expected one of {TICKETS}")
    return ticket


def ro_uri(path: Path) -> str:
    return Path(path).resolve().as_uri() + "?mode=ro"


def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(ro_uri(path), uri=True)


def _on_rm_error(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def rmtree(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    shutil.rmtree(path, onerror=_on_rm_error)


def make_readonly(path: Path) -> None:
    os.chmod(path, stat.S_IREAD)


def make_writable(path: Path) -> None:
    if Path(path).exists():
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def inside(base: Path, candidate: Path) -> bool:
    try:
        Path(candidate).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False
