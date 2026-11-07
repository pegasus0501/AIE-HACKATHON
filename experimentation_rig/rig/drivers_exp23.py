"""Drivers for experiments 2 and 3."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import common

AS_OF = common.AS_OF


def _exec_reports(repo: Path) -> dict:
    """Load src/reports.py from a cloned repo in an isolated namespace (no sys.modules pollution)."""
    path = repo / "src" / "reports.py"
    ns: dict = {"__name__": "rig_probe_reports", "__file__": str(path)}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)
    return ns


def collect(ticket: str, result) -> dict:
    if ticket != "exp2":
        raise NotImplementedError(f"no driver for {ticket} yet")
    repo = Path(result.work_dir) / "repo"
    ns = _exec_reports(repo)
    conn = sqlite3.connect(result.work_db)
    try:
        rows = ns["best_customers_by_region"](conn, AS_OF)
    except Exception as exc:  # the mutant may raise; invariants treat that as "no safe output"
        rows = None
        error = str(exc)
    else:
        error = None
    return {"rows": rows, "error": error, "db": result.work_db}
