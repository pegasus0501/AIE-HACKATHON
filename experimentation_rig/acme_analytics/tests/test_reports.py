from src import reports


def test_monthly_revenue_covers_known_months(conn):
    months = {m for m, _ in reports.monthly_revenue(conn)}
    assert {"2023-01", "2024-06", "2025-01"} <= months


def test_monthly_revenue_has_values(conn):
    assert all(revenue is not None for _, revenue in reports.monthly_revenue(conn))


def test_orders_by_source_lists_main_channels(conn):
    sources = {row[0] for row in reports.orders_by_source(conn)}
    assert {"web", "mobile", "marketplace"} <= sources


def test_top_products_limit(conn):
    rows = reports.top_products(conn, limit=5)
    assert len(rows) == 5
    assert rows[0][2] >= rows[-1][2]


def test_customer_summary_unknown_customer(conn):
    assert reports.customer_summary(conn, -1) is None


def test_amounts_castable(conn):
    count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE amount IS NOT NULL AND CAST(amount AS REAL) IS NULL"
    ).fetchone()[0]
    assert count == 0
