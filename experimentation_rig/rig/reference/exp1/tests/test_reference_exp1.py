"""Hidden reference tests for experiment 1 (orders.amount TEXT -> REAL). Expected values come from truth.db."""
import os
import shutil
import sqlite3

import pytest

from src import migrate
from src.db import connect


@pytest.fixture(scope="module")
def truth():
    path = os.environ.get("RIG_TRUTH_DB")
    if not path:
        pytest.skip("RIG_TRUTH_DB not set")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _expect(truth, conn, tag):
    """Yield (order_id, amount, expect_cents, expect_quarantine, quarantined) for a tag (None = untagged)."""
    cond = "tag IS NULL" if tag is None else "tag = ?"
    args = () if tag is None else (tag,)
    rows = truth.execute(
        f"SELECT order_id, expect_cents, expect_quarantine FROM truth_orders WHERE {cond}", args
    ).fetchall()
    amounts = {r[0]: r[1] for r in conn.execute("SELECT order_id, amount FROM orders")}
    quarantined = {r[0] for r in conn.execute("SELECT order_id FROM orders_amount_quarantine")}
    for r in rows:
        yield r["order_id"], amounts.get(r["order_id"], "MISSING"), r["expect_cents"], r["expect_quarantine"], \
            r["order_id"] in quarantined


def _check_tag(truth, conn, tag):
    wrong = []
    for oid, amount, cents, expect_q, quarantined in _expect(truth, conn, tag):
        if amount == "MISSING":
            wrong.append((oid, "row missing"))
        elif cents is None:
            if amount is not None:
                wrong.append((oid, f"expected NULL, got {amount!r}"))
        else:
            if amount is None or round(amount * 100) != cents or round(amount, 2) != amount:
                wrong.append((oid, f"expected {cents / 100:.2f}, got {amount!r}"))
        if bool(expect_q) != quarantined:
            wrong.append((oid, f"quarantine expected={bool(expect_q)} actual={quarantined}"))
    assert not wrong, f"{len(wrong)} rows wrong for {tag}: {wrong[:5]}"


def test_row_count_unchanged(conn, baseline_path):
    before = sqlite3.connect(baseline_path).execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == before


def test_other_columns_unchanged(conn, baseline_path):
    b = sqlite3.connect(baseline_path)
    cols = "order_id, customer_id, order_date, currency, status, source_system"
    old = b.execute(f"SELECT {cols} FROM orders ORDER BY order_id").fetchall()
    new = conn.execute(f"SELECT {cols} FROM orders ORDER BY order_id").fetchall()
    assert [tuple(r) for r in new] == old


def test_column_is_numeric(conn):
    kinds = {r[0] for r in conn.execute("SELECT DISTINCT typeof(amount) FROM orders")}
    assert kinds <= {"real", "integer", "null"}
    decl = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(orders)")}["amount"]
    assert decl.upper() in ("REAL", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE")


def test_untagged_rows_converted_exactly(truth, conn):
    _check_tag(truth, conn, None)


def test_L1_01_symbols_and_thousands_commas(truth, conn):
    _check_tag(truth, conn, "L1-01")


def test_L1_02_scientific_notation(truth, conn):
    _check_tag(truth, conn, "L1-02")


def test_L1_03_decimal_comma_source(truth, conn):
    _check_tag(truth, conn, "L1-03")


def test_L1_04_accounting_negatives(truth, conn):
    _check_tag(truth, conn, "L1-04")


def test_L1_05_blanks_are_quarantined_not_zeroed(truth, conn):
    _check_tag(truth, conn, "L1-05")
    zeros = conn.execute("SELECT COUNT(*) FROM orders WHERE amount = 0").fetchone()[0]
    assert zeros == 0


def test_L1_06_invisible_characters(truth, conn):
    _check_tag(truth, conn, "L1-06")


def test_L1_07_minor_unit_source(truth, conn):
    _check_tag(truth, conn, "L1-07")


def test_L1_08_unknown_placeholders(truth, conn):
    _check_tag(truth, conn, "L1-08")
    assert conn.execute("SELECT COUNT(*) FROM orders WHERE amount IN (-1, -999)").fetchone()[0] == 0


def test_L1_09_currency_codes(truth, conn):
    _check_tag(truth, conn, "L1-09")


def test_L1_10_three_decimal_rounding(truth, conn):
    _check_tag(truth, conn, "L1-10")


def test_L1_11_dependent_objects_survive(conn, baseline_path):
    b = sqlite3.connect(baseline_path)
    wanted = {(r[0], r[1]) for r in b.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('index','view','trigger') "
        "AND name NOT LIKE 'sqlite_%'")}
    have = {(r[0], r[1]) for r in conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('index','view','trigger')")}
    assert wanted <= have, f"missing: {sorted(wanted - have)}"
    assert conn.execute("SELECT COUNT(*) FROM v_monthly_revenue").fetchone()[0] > 0
    customer = conn.execute("SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1").fetchone()[0]
    audit_before = conn.execute("SELECT COUNT(*) FROM customers_audit").fetchone()[0]
    conn.execute("INSERT INTO orders (customer_id, order_date, amount, status, source_system) "
                 "VALUES (?, '2025-06-01', 10.0, 'completed', 'web')", (customer,))
    assert conn.execute("SELECT COUNT(*) FROM customers_audit").fetchone()[0] == audit_before + 1


def test_per_source_totals_reconcile(conn):
    rows = conn.execute(
        """
        SELECT o.source_system,
               COUNT(*) AS n,
               ROUND(SUM(o.amount), 2) AS converted,
               ROUND(SUM((SELECT SUM(ROUND(i.quantity * CAST(i.unit_price AS REAL) * (1 - COALESCE(i.discount_pct, 0) / 100.0), 2))
                          FROM order_items i WHERE i.order_id = o.order_id)), 2) AS items
        FROM orders o WHERE o.amount IS NOT NULL GROUP BY o.source_system
        """
    ).fetchall()
    assert rows
    for source, n, converted, items in rows:
        # one cent of rounding slack per order
        assert abs(converted - items) <= 0.01 * n, f"{source}: converted {converted} vs items {items}"


def test_foreign_keys_still_consistent(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_quarantine_has_one_row_per_order(conn):
    dup = conn.execute("SELECT COUNT(*) FROM (SELECT order_id FROM orders_amount_quarantine "
                       "GROUP BY order_id HAVING COUNT(*) > 1)").fetchone()[0]
    assert dup == 0
    assert conn.execute("SELECT COUNT(*) FROM orders_amount_quarantine WHERE reason IS NULL OR reason = ''").fetchone()[0] == 0


def test_down_migration_restores_text(db_path):
    c = connect(db_path)
    try:
        before = c.execute("SELECT order_id, amount FROM orders ORDER BY order_id").fetchall()
        migrate.down(c, 1)
        decl = {r[1]: r[2] for r in c.execute("PRAGMA table_info(orders)")}["amount"]
        assert decl.upper() == "TEXT"
        assert c.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == len(before)
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
        assert {"idx_orders_amount", "v_orders_clean", "v_monthly_revenue", "trg_orders_touch_customer"} <= names
        assert "005" not in migrate.applied_versions(c)
    finally:
        c.close()
