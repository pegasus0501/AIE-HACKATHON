"""Checks that nothing agent-visible gives the planted problems away."""
from __future__ import annotations

import re
import sqlite3

import yaml

from . import common, workspace

BANNED = re.compile(
    r"\b(?:dirty|messy|trap|landmine|bug|hack|workaround|todo|fixme|malformed|bad)(?:s)?\b", re.IGNORECASE
)


def _scan_text(label: str, text: str, problems: list) -> None:
    for n, line in enumerate(text.splitlines(), 1):
        m = BANNED.search(line)
        if m:
            problems.append(f"banned word {m.group(0)!r} in {label}:{n}")


def scan_repos(problems: list) -> int:
    count = 0
    for base in (common.TEMPLATE_DIR, common.REPO_DIR):
        if not base.exists():
            continue
        for rel, text in workspace.read_tree(base).items():
            count += 1
            _scan_text(f"{base.name}/{rel}", text, problems)
    return count


def scan_workspace_output(problems: list) -> int:
    count = 0
    for ticket in common.TICKETS:
        if not (common.TICKETS_DIR / f"{ticket}.md").exists():
            continue
        for role in ("engineer", "tester"):
            for rel, text in workspace.build(ticket, role).items():
                count += 1
                if rel in ("TICKET.md", "CONTRACT.md"):
                    _scan_text(f"workspace[{ticket}/{role}]/{rel}", text, problems)
    return count


def scan_schema_names(problems: list) -> int:
    if not common.ACME_DB.exists():
        problems.append("no database to scan; run seed first")
        return 0
    conn = common.connect_ro(common.ACME_DB)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master")]
        for t in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
            names += [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')]
    finally:
        conn.close()
    for name in names:
        if BANNED.search(name):
            problems.append(f"banned word in schema name {name!r}")
    return len(names)


def _load_keys() -> dict:
    keys = {}
    for ticket in common.TICKETS:
        path = common.KEY_DIR / f"{ticket}.yaml"
        if path.exists():
            keys[ticket] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return keys


def check_runs_and_fractions(problems: list) -> dict:
    """Planted ids must not form runs longer than 2 and each dirty fraction must stay under its threshold."""
    stats = {}
    if not common.ACME_DB.exists():
        return stats
    conn = common.connect_ro(common.ACME_DB)
    try:
        for ticket, key in _load_keys().items():
            for lm in key.get("landmines", []):
                lid = lm["id"]
                if lm.get("ids_sql"):
                    ids = sorted(r[0] for r in conn.execute(lm["ids_sql"]))
                    run = best = 1 if ids else 0
                    for a, b in zip(ids, ids[1:]):
                        run = run + 1 if b == a + 1 else 1
                        best = max(best, run)
                    if best > 2:
                        problems.append(f"{lid}: planted ids contain a run of {best} consecutive ids")
                    rounds = [i for i in ids if i % 100 == 0]
                    if rounds:
                        problems.append(f"{lid}: round-number planted ids {rounds[:3]}")
                if lm.get("population_sql") and lm.get("max_fraction") is not None:
                    dirty = conn.execute(lm["probe_sql"]).fetchone()[0]
                    pop = conn.execute(lm["population_sql"]).fetchone()[0]
                    frac = dirty / pop if pop else 0.0
                    stats[lid] = round(frac, 5)
                    if frac > lm["max_fraction"]:
                        problems.append(f"{lid}: dirty fraction {frac:.4f} exceeds {lm['max_fraction']}")
    finally:
        conn.close()
    return stats


def run() -> dict:
    problems: list = []
    repo_files = scan_repos(problems)
    ws_files = scan_workspace_output(problems)
    names = scan_schema_names(problems)
    stats = check_runs_and_fractions(problems)
    return {"ok": not problems, "problems": problems, "repo_files_scanned": repo_files,
            "workspace_files_scanned": ws_files, "schema_names_scanned": names, "fractions": stats}
