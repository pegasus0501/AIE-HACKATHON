"""Append-only event log shared by all three agents (one JSON object per line)."""

import json
import os
from datetime import datetime, timezone


def log_event(kind: str, **fields) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **fields}
    with open(os.getenv("EVENTS_FILE", "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
