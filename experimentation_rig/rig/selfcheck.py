"""Does the rig itself work? Reference passes, every mutant fails, invariants fire, key matches the data."""
from __future__ import annotations

import hashlib
import sqlite3

from . import common, invariants, mutgen, workspace
from .score import hidden_tests, load_key
from .run import run_in_clone


def _digest(tree: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(tree):
        h.update(k.encode()); h.update(tree[k].encode())
    return h.hexdigest()


class Report:
    def __init__(self):
        self.rows: list = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail})

    @property
    def ok(self) -> bool:
        return all(r["ok"] for r in self.rows)


def check_key_against_data(ticket: str, rep: Report) -> dict:
    """Probe results per landmine, and per-tier totals."""
    key = load_key(ticket)
    conn = common.connect_ro(common.ACME_DB)
    truth_conn = common.connect_ro(common.TRUTH_DB) if common.TRUTH_DB.exists() else None
    tiers: dict = {}
    try:
        for lm in key["landmines"]:
            probe_conn = truth_conn if lm.get("db") == "truth" else conn
            got = probe_conn.execute(lm["probe_sql"]).fetchone()[0]
            rep.add(f"{ticket} key {lm['id']} probe", got == lm["expected_probe_result"],
                    f"expected {lm['expected_probe_result']}, got {got}")
            tiers[lm["tier"]] = tiers.get(lm["tier"], 0) + 1
            if lm.get("exposed_by") in (None, []):
                rep.add(f"{ticket} key {lm['id']} exposed_by", False, "no exposed_by invariant")
    finally:
        conn.close()
        if truth_conn:
            truth_conn.close()
    if common.TRUTH_DB.exists():
        t = sqlite3.connect(common.TRUTH_DB)
        plants = dict(t.execute("SELECT landmine_id, n FROM plants"))
        t.close()
        for lm in key["landmines"]:
            if lm["id"] in plants:
                rep.add(f"{ticket} truth count {lm['id']}", plants[lm["id"]] == lm["expected_probe_result"],
                        f"truth {plants[lm['id']]} vs key {lm['expected_probe_result']}")
    return tiers


def selfcheck_ticket(ticket: str, rep: Report) -> None:
    key = load_key(ticket)
    reference = mutgen.reference_files(ticket)
    hidden = hidden_tests(ticket)
    tiers = check_key_against_data(ticket, rep)
    rep.add(f"{ticket} tier counts", True, str(dict(sorted(tiers.items()))))

    ref = run_in_clone(ticket, reference, hidden, keep_db=True, with_truth=True)
    try:
        rep.add(f"{ticket} reference passes hidden tests", ref.passed,
                "; ".join(f"{f['test']}: {f['message'][:120]}" for f in ref.failures[:3]))
        if ref.stage == "tests":
            all_names = sorted({n for lm in key["landmines"] for n in lm.get("exposed_by", [])})
            quiet = invariants.evaluate(ticket, all_names, ref)
            for name, viol in quiet.items():
                rep.add(f"{ticket} invariant {name} holds on reference", not viol, "; ".join(viol[:2]))
    finally:
        ref.cleanup()

    for lm in key["landmines"]:
        lid = lm["id"]
        files = mutgen.load_mutant(ticket, lid)
        if not files:
            rep.add(f"{ticket} mutant {lid} exists", False, "mutant folder missing; run: mutants")
            continue
        diff = [k for k in reference if files.get(k) != reference[k]]
        rep.add(f"{ticket} mutant {lid} differs from reference", bool(diff), ", ".join(diff))
        m = run_in_clone(ticket, files, hidden, keep_db=True, with_truth=True)
        try:
            failing = sorted(t for t, o in m.tests.items() if o != "passed")
            tag = lid.replace("-", "_")
            own = [t for t in failing if tag in t]
            rep.add(f"{ticket} mutant {lid} fails reference tests", bool(failing),
                    f"failing: {failing[:4]}")
            if m.stage == "tests":
                fired = invariants.evaluate(ticket, lm["exposed_by"], m)
                rep.add(f"{ticket} mutant {lid} violates exposed_by", any(fired.values()),
                        ", ".join(f"{k}={len(v)}" for k, v in fired.items()))
        finally:
            m.cleanup()


def run(tickets=None) -> dict:
    rep = Report()
    if not common.ACME_DB.exists():
        rep.add("database present", False, "run seed first")
        return {"ok": False, "checks": rep.rows}
    template = workspace.read_tree(common.TEMPLATE_DIR)
    if common.REPO_DIR.exists():
        rep.add("acme_analytics matches pristine template",
                _digest(workspace.read_tree(common.REPO_DIR)) == _digest(template),
                "differs; run reset to regenerate")
    for ticket in tickets or [t for t in common.TICKETS if (common.KEY_DIR / f"{t}.yaml").exists()]:
        if not (common.REFERENCE_DIR / ticket).exists():
            rep.add(f"{ticket} built", False, "no reference folder")
            continue
        selfcheck_ticket(ticket, rep)
    return {"ok": rep.ok, "checks": rep.rows}
