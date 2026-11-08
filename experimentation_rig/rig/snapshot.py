"""Frozen copies of the base database, one per ticket."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import common


def path_for(ticket: str) -> Path:
    """Snapshot for the ticket if it exists, otherwise the base database."""
    common.check_ticket(ticket)
    snap = common.SNAPSHOT_DIR / f"{ticket}.db"
    if snap.exists():
        return snap
    if common.ACME_DB.exists():
        return common.ACME_DB
    raise FileNotFoundError("no database yet; run: python -m experimentation_rig.rig seed")


def snapshot(ticket: str) -> Path:
    common.check_ticket(ticket)
    if not common.ACME_DB.exists():
        raise FileNotFoundError("no database yet; run: python -m experimentation_rig.rig seed")
    common.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    target = common.SNAPSHOT_DIR / f"{ticket}.db"
    if target.exists():
        common.make_writable(target)
        target.unlink()
    shutil.copyfile(common.ACME_DB, target)
    common.make_readonly(target)
    return target
