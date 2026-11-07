# Rig status and known issues

Last verified: full `reset` (fresh database + fresh toy repo) followed by `selfcheck exp1`, `selfcheck exp2`,
and `tellscan`, all green. See `docs/rig-architecture.md` for the architecture and the full landmine catalog.

## Is it ready to use?

**Yes, for Experiment 1 and Experiment 2.** You can hand an Engineer agent and a Tester agent
`rig.workspace.build("exp1", "engineer" | "tester")` (or `"exp2"`) today and score their work with
`rig.score.score(...)`. Both experiments are self-verifying: the reference solution passes every hidden
test, every mutant fails its own hidden test, and `tellscan` confirms nothing agent-visible gives away which
rows are planted.

**No, for Experiment 3.** It was not built — no reference solution, no hidden tests, no mutants, no answer
key. `rig/tickets/exp3.md` and `rig/contracts/exp3.md` don't exist. Don't point agents at `"exp3"`; the CLI
will reject it with "no reference folder."

## How to run it as a real test

```
cd /path/to/repo
python -m experimentation_rig.rig reset          # fresh data + fresh acme_analytics/
python -m experimentation_rig.rig selfcheck exp1 # confirms the rig itself is sound, re-run anytime
python -m experimentation_rig.rig selfcheck exp2
```

Then, per experiment:
1. Give the Engineer `rig.workspace.build(ticket, "engineer")` (the toy repo + `TICKET.md` + `CONTRACT.md`).
   It may write only `migrations/`, `queries/`, `src/`.
2. Give the Tester the same, but it may write only `tests/`. Both agents may call
   `rig.readonly.query(ticket, sql)` to inspect the data (single `SELECT`, row/time limited).
3. Collect `engineer_files` and `tester_files` as `{path: file_text}` dicts.
4. `rig.score.score(ticket, engineer_files, tester_files)` returns the full report: catch rate, catch rate
   by tier, false alarms, whether the Engineer's patch passes the hidden tests, and which generic invariants
   fired per landmine.

## Known issues and limitations

### Significant
- **Experiment 3 doesn't exist.** Not a bug, just unbuilt. Building it would reuse the duplicate-customer
  data already planted for Experiment 2's L2-08.
- **Exp2 invariants lean on `truth.db`.** Several of the 12 "generic invariant" checks for Experiment 2
  (e.g. `window_matches_payment_dates`, `no_date_rows_dropped`) compare the agent's output against the rig's
  own ground-truth table rather than re-deriving the right answer from raw SQL independently. This is safe —
  `truth.db` is rig-internal and never shown to any agent — but it means those specific invariants are a
  weaker signal of "would a human without the answer key have caught this" than the Experiment 1 invariants,
  which are fully independent reconciliation checks. It does **not** affect the actual catch/no-catch
  scoring, which is based purely on hidden tests passing or failing.
- **No regression guard between experiments.** Both experiments share one `acme.db`. I verified Experiment 1
  stays green after adding Experiment 2's data plants, but there's no automated check that a future change to
  one experiment's seeding can't silently break the other. If you extend the rig, re-run both selfchecks.

### Minor
- A few of Experiment 2's reference-code mutants (e.g. `L2-02`, `L2-11`) are only loosely "realistic" —
  they're the smallest edit that reproduces the described failure mode, not necessarily a bug a human would
  plausibly write. This matches the spec's definition ("the reference with exactly that landmine mishandled")
  but is worth knowing if you expect mutants to look like natural engineer mistakes.
- `orders.amount` is still `TEXT` in the base snapshot used by Experiment 2 (Experiment 1's migration isn't
  applied there) — intentional per each experiment having its own ticket, but means Experiment 2's revenue
  math reads `payments.amount` (already numeric) rather than `orders.amount`, not the raw TEXT column.
- Dev scratch scripts used while debugging (`_dev_*.py`) were deleted before commit; none remain in the repo.

### Not yet exercised
- The rig has never been run end-to-end with an actual LLM-driven Engineer/Tester pair — only with the
  reference solution and the mutants standing in for "Engineer." The agent-facing surface
  (`workspace.build`, `readonly.query`, path allowlisting in `run_in_clone`) is implemented and unit-tested
  via selfcheck, but a live run is the first real test of the full loop.

## Suggested next step

Run one live experiment end-to-end (Experiment 1 is simpler — one migration file, 11 landmines) with a real
Engineer and Tester agent pair pointed at `rig.workspace.build`, and check the `score()` output makes sense
before relying on Experiment 2's more elaborate reporting logic.
