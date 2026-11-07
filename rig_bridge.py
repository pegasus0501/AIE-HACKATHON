"""Thin adapter between the agents and experimentation_rig. Imported lazily; free-form tasks never need it."""

import re
from pathlib import Path

ISSUES = ("exp1", "exp2")  # exp3 is not built (see experimentation_rig/STATUS.md)
MAX_FILE_CHARS = 4000
MAX_CONTEXT_CHARS = 22000
SKIP_IN_CONTEXT = ("TICKET.md", "CONTRACT.md", "db/schema.sql")  # schema comes from schema_text()


def _rig():
    from experimentation_rig.rig import common, readonly, score, snapshot, workspace
    from experimentation_rig.rig.run import run_in_clone

    return common, readonly, score, snapshot, workspace, run_in_clone


def is_issue(ticket_id: str) -> bool:
    return ticket_id in ISSUES


def ticket_text(ticket_id: str) -> str:
    return (_rig()[0].TICKETS_DIR / f"{ticket_id}.md").read_text(encoding="utf-8").strip()


def contract_text(ticket_id: str) -> str:
    return (_rig()[0].CONTRACTS_DIR / f"{ticket_id}.md").read_text(encoding="utf-8").strip()


def title(ticket_id: str) -> str:
    first = ticket_text(ticket_id).splitlines()[0]
    return re.sub(r"^#\s*(Ticket:\s*)?", "", first).strip() or ticket_id


def issues() -> list[dict]:
    return [{"id": i, "title": title(i)} for i in ISSUES]


def repo_context(ticket_id: str, role: str) -> str:
    """Schema plus the repo files the role may see. Never includes anything from rig/ or the answer key."""
    _, _, _, _, workspace, _ = _rig()
    files = workspace.build(ticket_id, role)
    parts = ["DATABASE SCHEMA (current):\n" + workspace.schema_text(ticket_id)]
    parts.append("REPOSITORY FILES:\n" + "\n".join(sorted(files)))
    used = sum(len(p) for p in parts)
    for name in sorted(files):
        if name in SKIP_IN_CONTEXT or name.endswith(".sql") and name.startswith("migrations/"):
            continue
        body = files[name][:MAX_FILE_CHARS]
        if used + len(body) > MAX_CONTEXT_CHARS:
            break
        used += len(body)
        parts.append(f"--- {name} ---\n{body}")
    return "\n\n".join(parts)


def sql(ticket_id: str, query: str, max_show: int = 25) -> str:
    """Run one read-only SELECT against the ticket's frozen snapshot; return text for the model."""
    _, readonly, _, _, _, _ = _rig()
    try:
        r = readonly.query(ticket_id, query)
    except Exception as e:  # QueryRejected, sqlite errors, timeouts
        return f"ERROR: {type(e).__name__}: {e}"
    rows = r["rows"][:max_show]
    lines = [" | ".join(r["columns"])] + [" | ".join("NULL" if v is None else str(v) for v in row) for row in rows]
    note = f"\n({len(r['rows'])} row(s) returned" + (", truncated by the rig" if r.get("truncated") else "")
    note += f", showing {len(rows)})" if len(r["rows"]) > len(rows) else ")"
    return "\n".join(lines) + note


def run_round(ticket_id: str, engineer_files: dict, tester_files: dict) -> dict:
    """Apply both agents' files to a clone of the repo and database, migrate, run pytest."""
    *_, run_in_clone = _rig()
    r = run_in_clone(ticket_id, engineer_files, tester_files)
    lines = []
    for f in r.failures[:20]:
        raw = " ".join((f.get("message") or "").split())
        # a crash traceback carries its real error at the END; a failed assertion carries it at the start
        msg = raw[-400:] if f["test"] in ("migrations", "suite") else raw[:300]
        lines.append(f"FAILED {f['test']}" + (f": {msg}" if msg else ""))
    if r.stage != "tests":
        lines.insert(0, f"stage '{r.stage}' failed before the tests could run")
    return {"passed": bool(r.passed), "report": "\n".join(lines), "stage": r.stage, "tests": len(r.tests)}


def score(ticket_id: str, engineer_files: dict, tester_files: dict) -> dict:
    return _rig()[2].score(ticket_id, engineer_files, tester_files)
