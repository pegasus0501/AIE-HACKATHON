# Contributing

## Conventions

* Every migration ships with an up file and a down file. Run `python scripts/check_migrations.py` before
  opening a change.
* SQL used by reports goes in `queries/`. Application code goes in `src/`.
* Functions in `src/procedures.py` commit on success and roll back on error.
* Tests live in `tests/` and use the `conn` fixture, which gives each test its own copy of the database.
* Keep functions small and name tests after the behavior they check.

## Customer records

* Any operation that merges or removes customer records must write one row to `customers_merge_log` for each
  record removed: `survivor_id`, `merged_id`, `merged_at` and a short `details` text.
* The database connection from `src/db.py` has foreign keys enabled.

## Reviews

Describe the change, list the migrations it adds, and say how it was tested.
