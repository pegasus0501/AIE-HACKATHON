"""Score a Tester suite against the planted problems of a ticket.

A landmine is CAUGHT when some Tester test fails on that landmine's mutant while passing on the reference
solution. With no false alarms this is identical to "the suite fails on the mutant and passes on the
reference"; the per-test form keeps one false alarm from erasing every catch (false alarms are reported).
"""
from __future__ import annotations

from collections import defaultdict

import yaml

from . import common, invariants, mutgen, workspace
from .run import run_in_clone


def load_key(ticket: str) -> dict:
    return yaml.safe_load((common.KEY_DIR / f"{ticket}.yaml").read_text(encoding="utf-8"))


def hidden_tests(ticket: str) -> dict:
    tree = workspace.read_tree(common.REFERENCE_DIR / ticket)
    return {k: v for k, v in tree.items() if k.startswith("tests/")}


def score(ticket: str, engineer_files: dict, tester_files: dict) -> dict:
    key = load_key(ticket)
    reference = mutgen.reference_files(ticket)

    ref_run = run_in_clone(ticket, reference, tester_files)
    ref_passed = {t for t, o in ref_run.tests.items() if o == "passed"}
    false_alarms = [f for f in ref_run.failures]

    eng_run = run_in_clone(ticket, engineer_files, hidden_tests(ticket), with_truth=True)

    per_landmine = []
    for lm in key["landmines"]:
        lid = lm["id"]
        files = mutgen.load_mutant(ticket, lid)
        mrun = run_in_clone(ticket, files, tester_files, keep_db=True)
        try:
            failed_on_mutant = {t for t, o in mrun.tests.items() if o != "passed"}
            caught_by = sorted(failed_on_mutant & ref_passed)
            fired = []
            if mrun.stage == "tests":
                for name, violations in invariants.evaluate(ticket, lm.get("exposed_by", []), mrun).items():
                    if violations:
                        fired.append(name)
        finally:
            mrun.cleanup()
        per_landmine.append({"id": lid, "tier": lm["tier"], "caught": bool(caught_by),
                             "caught_by_tests": caught_by, "invariants_fired": fired})

    by_tier: dict = defaultdict(lambda: [0, 0])
    for row in per_landmine:
        by_tier[row["tier"]][1] += 1
        by_tier[row["tier"]][0] += int(row["caught"])
    caught = sum(r["caught"] for r in per_landmine)
    return {
        "ticket": ticket,
        "caught": caught,
        "total": len(per_landmine),
        "catch_rate": round(caught / len(per_landmine), 3) if per_landmine else 0.0,
        "catch_rate_by_tier": {t: {"caught": c, "total": n, "rate": round(c / n, 3)} for t, (c, n) in sorted(by_tier.items())},
        "false_alarms": false_alarms,
        "tester_suite_passes_on_reference": ref_run.passed,
        "engineer_passes_hidden_tests": eng_run.passed,
        "engineer_hidden_failures": [f["test"] for f in eng_run.failures],
        "landmines": per_landmine,
    }
