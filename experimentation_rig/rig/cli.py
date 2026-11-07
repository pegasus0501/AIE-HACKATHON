"""Command line: python -m experimentation_rig.rig <command> (run from the repository root)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import common


def _tree(path) -> dict:
    from .workspace import read_tree
    return read_tree(path) if path else {}


def cmd_seed(args) -> int:
    from . import seed
    seed.main()
    return 0


def cmd_reset(args) -> int:
    from . import seed
    common.rmtree(common.REPO_DIR)
    shutil.copytree(common.TEMPLATE_DIR, common.REPO_DIR,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
    for p in (common.ACME_DB, common.TRUTH_DB):
        common.make_writable(p)
        if p.exists():
            p.unlink()
    common.rmtree(common.SNAPSHOT_DIR)
    common.rmtree(common.WORK_DIR)
    seed.main()
    print(f"regenerated {common.REPO_DIR.name}/ from {common.TEMPLATE_DIR.name}/")
    return 0


def cmd_snapshot(args) -> int:
    from . import snapshot
    print(snapshot.snapshot(args.ticket))
    return 0


def _files_for(args):
    from . import mutgen
    if getattr(args, "reference", False):
        eng = mutgen.reference_files(args.ticket)
    elif getattr(args, "mutant", None):
        eng = mutgen.load_mutant(args.ticket, args.mutant)
    else:
        eng = _tree(args.engineer)
    return eng, _tree(args.tester)


def cmd_run(args) -> int:
    from .run import run_in_clone
    eng, tst = _files_for(args)
    result = run_in_clone(args.ticket, eng, tst, with_truth=args.hidden)
    print(json.dumps({"passed": result.passed, "stage": result.stage, "failures": result.failures,
                      "tests": result.tests}, indent=2))
    return 0 if result.passed else 1


def cmd_score(args) -> int:
    from .score import score
    eng, tst = _files_for(args)
    print(json.dumps(score(args.ticket, eng, tst), indent=2))
    return 0


def cmd_selfcheck(args) -> int:
    from . import selfcheck
    out = selfcheck.run([args.ticket] if args.ticket else None)
    for row in out["checks"]:
        print(("PASS " if row["ok"] else "FAIL ") + row["check"] + (f"  [{row['detail']}]" if row["detail"] else ""))
    print("SELFCHECK", "GREEN" if out["ok"] else "RED")
    return 0 if out["ok"] else 1


def cmd_tellscan(args) -> int:
    from . import tellscan
    out = tellscan.run()
    for p in out["problems"]:
        print("FAIL", p)
    print(f"scanned {out['repo_files_scanned']} repo files, {out['workspace_files_scanned']} workspace files, "
          f"{out['schema_names_scanned']} schema names; dirty fractions: {out['fractions']}")
    print("TELLSCAN", "GREEN" if out["ok"] else "RED")
    return 0 if out["ok"] else 1


def cmd_mutants(args) -> int:
    from . import mutgen
    print(mutgen.generate())
    return 0


def cmd_query(args) -> int:
    from . import readonly
    print(json.dumps(readonly.query(args.ticket, args.sql), indent=2, default=str))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m experimentation_rig.rig")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="build data/acme.db and data/truth.db").set_defaults(fn=cmd_seed)
    sub.add_parser("reset", help="regenerate acme_analytics/ from the template and rebuild the database").set_defaults(fn=cmd_reset)
    s = sub.add_parser("snapshot", help="freeze a read-only copy of the database for a ticket")
    s.add_argument("ticket", choices=common.TICKETS); s.set_defaults(fn=cmd_snapshot)
    for name, fn, helptext in (("run", cmd_run, "run engineer/tester files on a throwaway clone"),
                               ("score", cmd_score, "score a tester suite against the planted problems")):
        r = sub.add_parser(name, help=helptext)
        r.add_argument("ticket", choices=common.TICKETS)
        r.add_argument("--engineer", help="folder with the engineer's files (migrations/, queries/, src/)")
        r.add_argument("--tester", help="folder with the tester's files (tests/)")
        r.add_argument("--reference", action="store_true", help="use the reference solution as the engineer")
        r.add_argument("--mutant", help="use the mutant for this landmine id as the engineer")
        r.add_argument("--hidden", action="store_true", help="expose truth.db (for hidden reference tests)")
        r.set_defaults(fn=fn)
    c = sub.add_parser("selfcheck", help="verify the rig itself")
    c.add_argument("ticket", nargs="?", choices=common.TICKETS); c.set_defaults(fn=cmd_selfcheck)
    sub.add_parser("tellscan", help="check that nothing agent-visible gives the planted problems away").set_defaults(fn=cmd_tellscan)
    sub.add_parser("mutants", help="regenerate mutants/ from reference/").set_defaults(fn=cmd_mutants)
    q = sub.add_parser("query", help="run one read-only SELECT against a ticket snapshot")
    q.add_argument("ticket", choices=common.TICKETS); q.add_argument("sql"); q.set_defaults(fn=cmd_query)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
