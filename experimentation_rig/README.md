# experimentation_rig

A harness for running two AI agents (Engineer, Tester) against a toy e-commerce database and scoring which
planted data problems the Tester actually catches. See `docs/rig-architecture.md` for the data model, the
agent-facing API, and the full landmine catalog.

## Setup

```
cd experimentation_rig
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env     # optional, defaults are fine
```

Requires Python 3.9+ and SQLite 3.25+ (for window functions). Tested with Python 3.13.3 / SQLite 3.49.1.

## Commands

Run from the **repository root** (the parent of `experimentation_rig/`), using the venv's Python:

```
python -m experimentation_rig.rig seed                  # build data/acme.db and data/truth.db
python -m experimentation_rig.rig reset                  # regenerate acme_analytics/ from the template + reseed
python -m experimentation_rig.rig snapshot exp1           # freeze a read-only snapshot for a ticket
python -m experimentation_rig.rig mutants                 # regenerate mutants/ from reference/
python -m experimentation_rig.rig query exp1 "SELECT ..."  # one read-only SELECT against a ticket snapshot

python -m experimentation_rig.rig run exp1 --reference --tester path/to/tester_files
python -m experimentation_rig.rig score exp1 --engineer path/to/engineer_files --tester path/to/tester_files

python -m experimentation_rig.rig selfcheck exp1    # or exp2; verifies the rig itself
python -m experimentation_rig.rig tellscan          # checks nothing agent-visible leaks the landmines
```

`--engineer`/`--tester` point at folders whose contents become the files dict (path relative to the folder).
`--reference` uses the reference solution as the engineer. `--mutant <id>` uses a specific mutant instead.

## Everything here is self-contained

- Only this folder is read or written. No other code in the parent repository is imported or modified.
- `acme_analytics_template/` is the pristine toy repo and is never edited after generation; `reset`
  regenerates `acme_analytics/` from it and rebuilds the database from scratch.
- `data/*.db`, `data/work/`, `data/snapshots/`, `.env`, `__pycache__/`, `.pytest_cache/` and `.venv/` are
  all git-ignored by this folder's own `.gitignore`.
- Dependencies (`pytest`, `PyYAML`) are listed in `requirements.txt` and installed only into this folder's
  own virtual environment, never globally.

## Status

Experiment 1 (orders.amount → numeric) and Experiment 2 (best customers per region) are complete:
`selfcheck exp1`, `selfcheck exp2`, and `tellscan` are all green. Experiment 3 (merge duplicate customers)
has not been built. See the final report in the pull request / commit message for details.
