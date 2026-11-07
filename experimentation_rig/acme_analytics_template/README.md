# acme-analytics

Reporting and maintenance code for the Acme store database (SQLite).

## Layout

| Path | Purpose |
|---|---|
| `db/schema.sql` | Current schema, for reference |
| `migrations/` | Numbered `NNN_name.up.sql` and `NNN_name.down.sql` files |
| `queries/` | Named SQL used by the reports |
| `src/` | Application code (`db`, `models`, `helpers`, `reports`, `procedures`, `migrate`) |
| `tests/` | pytest suite |
| `scripts/check_migrations.py` | Fails when a migration has no down file |

## Setup

Point the code at a database file with the `DATABASE_PATH` environment variable. If it is not set, the code
uses `../data/acme.db` relative to this folder.

```
python -m src.migrate status
python -m src.migrate up
python -m pytest tests
```

## Migrations

* Files are applied in numeric order and recorded in the `schema_migrations` table.
* Migrations `001` to `004` are already applied to the shared database. New work starts at `005`.
* `python -m src.migrate down` rolls back the most recent migration using its down file.

## Reports and procedures

* `src/reports.py` holds read-only reporting functions.
* `src/procedures.py` holds multi-step operations that run in a single transaction.
