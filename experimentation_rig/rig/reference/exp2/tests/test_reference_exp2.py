"""Hidden reference tests for experiment 2 (best customers per region). Expected values come from truth.db."""
import os
import sqlite3

import pytest

from src.reports import best_customers_by_region

AS_OF = "2025-06-30"


@pytest.fixture(scope="module")
def truth():
    path = os.environ.get("RIG_TRUTH_DB")
    if not path:
        pytest.skip("RIG_TRUTH_DB not set")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def rows(conn):
    return {(r["region"], r["customer_id"]): r for r in best_customers_by_region(conn, AS_OF)}


@pytest.fixture
def truth_rows(truth):
    return {
        (r["region"], r["customer_id"]): dict(
            rank=r["rank"], net=round(r["net_cents"] / 100.0, 2), prior=round(r["prior_cents"] / 100.0, 2),
            pct_change=r["pct_change"], slipping=bool(r["slipping"]),
        )
        for r in truth.execute("SELECT * FROM truth_exp2_rows")
    }


def test_every_expected_row_present(rows, truth_rows):
    missing = set(truth_rows) - set(rows)
    assert not missing, f"missing rows: {sorted(missing)}"


def test_no_extra_rows(rows, truth_rows):
    extra = set(rows) - set(truth_rows)
    assert not extra, f"unexpected rows: {sorted(extra)}"


def test_rank_and_net_match(rows, truth_rows):
    wrong = []
    for key, expected in truth_rows.items():
        got = rows.get(key)
        if got is None:
            continue
        if got["rank"] != expected["rank"] or abs(got["net"] - expected["net"]) > 0.01:
            wrong.append((key, got, expected))
    assert not wrong, wrong[:5]


def test_prior_and_pct_change_match(rows, truth_rows):
    wrong = []
    for key, expected in truth_rows.items():
        got = rows.get(key)
        if got is None:
            continue
        if abs(got["prior"] - expected["prior"]) > 0.01:
            wrong.append((key, "prior", got["prior"], expected["prior"]))
        if (got["pct_change"] is None) != (expected["pct_change"] is None):
            wrong.append((key, "pct_change_none", got["pct_change"], expected["pct_change"]))
        elif got["pct_change"] is not None and abs(got["pct_change"] - expected["pct_change"]) > 0.1:
            wrong.append((key, "pct_change", got["pct_change"], expected["pct_change"]))
    assert not wrong, wrong[:5]


def test_slipping_matches(rows, truth_rows):
    wrong = [(k, rows[k]["slipping"], v["slipping"]) for k, v in truth_rows.items()
             if k in rows and rows[k]["slipping"] != v["slipping"]]
    assert not wrong, wrong[:5]


def test_ties_share_rank_and_all_included(conn):
    rows = best_customers_by_region(conn, AS_OF)
    by_region: dict = {}
    for r in rows:
        by_region.setdefault(r["region"], []).append(r)
    for region, members in by_region.items():
        by_rank: dict = {}
        for m in members:
            by_rank.setdefault(m["rank"], set()).add(round(m["net"], 2))
        for rank, nets in by_rank.items():
            # everyone returned at this rank must have the same net revenue
            assert len(nets) == 1, f"{region} rank {rank} has mismatched nets: {nets}"


def test_unassigned_customers_are_reported(conn):
    rows = best_customers_by_region(conn, AS_OF)
    assert any(r["region"] == "Unassigned" for r in rows)


def test_regions_are_rolled_up_to_top_level(conn):
    rows = best_customers_by_region(conn, AS_OF)
    top_level = {name for (_, name, parent) in conn.execute("SELECT region_id, name, parent_id FROM regions")
                 if parent is None}
    for r in rows:
        assert r["region"] == "Unassigned" or r["region"] in top_level, r["region"]


def test_negative_net_customer_is_present(conn):
    rows = best_customers_by_region(conn, AS_OF)
    assert any(r["net"] < 0 for r in rows)


def test_zero_prior_gives_defined_result(conn):
    rows = best_customers_by_region(conn, AS_OF)
    zero_prior = [r for r in rows if r["prior"] == 0]
    assert zero_prior
    for r in zero_prior:
        assert r["pct_change"] is None
        assert r["slipping"] is False


def test_pct_change_is_a_float_not_truncated(conn):
    rows = best_customers_by_region(conn, AS_OF)
    non_integer = [r for r in rows if r["pct_change"] is not None and abs(r["pct_change"] - round(r["pct_change"])) > 1e-9]
    assert non_integer, "expected at least one non-integer pct_change among the selected rows"


def test_duplicate_customers_are_combined(conn):
    rows = best_customers_by_region(conn, AS_OF)
    na = [r for r in rows if r["region"] == "North America"]
    ids = {r["customer_id"] for r in na}
    dup_pair = conn.execute(
        "SELECT c1.customer_id, c2.customer_id FROM customers c1 JOIN customers c2 "
        "ON c2.customer_id > c1.customer_id AND lower(trim(c2.email)) = lower(trim(c1.email)) "
        "WHERE c1.region_id IN (SELECT region_id FROM regions WHERE name = 'New England')"
    ).fetchone()
    assert dup_pair is not None
    assert dup_pair[1] not in ids, "the higher duplicate id should not appear as its own row"


def test_boundary_day_order_is_included(conn):
    cid = conn.execute(
        "SELECT o.customer_id FROM orders o WHERE o.order_date = '2025-04-01' "
        "AND o.customer_id IN (SELECT customer_id FROM customers WHERE region_id = 28) "
        "ORDER BY (SELECT COALESCE(SUM(p.amount), 0) FROM payments p JOIN orders o2 "
        "          ON o2.order_id = p.order_id WHERE o2.customer_id = o.customer_id "
        "          AND p.status = 'captured' AND o2.order_date BETWEEN '2025-04-02' AND '2025-06-30') "
        "DESC LIMIT 1"
    ).fetchone()
    assert cid is not None
    rows = best_customers_by_region(conn, AS_OF)
    assert any(r["customer_id"] == cid[0] for r in rows)
