"""Per-ticket drivers that turn a kept run (clone repo + migrated work copy) into an invariant state."""
from __future__ import annotations

from pathlib import Path


def collect(ticket: str, result) -> dict:
    if ticket == "exp1":
        return {"before": result.before_db, "after": result.work_db}
    from . import drivers_exp23
    return drivers_exp23.collect(ticket, result)
