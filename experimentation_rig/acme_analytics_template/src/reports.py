"""Reporting functions. SQL text lives in queries/*.sql."""
from __future__ import annotations

from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parents[1] / "queries"


def load_query(name: str) -> str:
    return (QUERIES_DIR / f"{name}.sql").read_text(encoding="utf-8")


def monthly_revenue(conn):
    """Revenue per month as a list of (month, revenue) tuples."""
    return [(r[0], r[1]) for r in conn.execute(load_query("monthly_revenue"))]


def orders_by_source(conn):
    """Order count and revenue per source system."""
    sql = (
        "SELECT source_system, COUNT(*) AS order_count, ROUND(SUM(CAST(amount AS REAL)), 2) AS revenue "
        "FROM orders WHERE status <> 'cancelled' GROUP BY source_system ORDER BY source_system"
    )
    return [tuple(r) for r in conn.execute(sql)]


def top_products(conn, limit: int = 10):
    """Best selling products by units sold."""
    sql = (
        "SELECT p.product_id, p.name, SUM(i.quantity) AS units "
        "FROM order_items i JOIN products p ON p.product_id = i.product_id "
        "GROUP BY p.product_id, p.name ORDER BY units DESC, p.product_id LIMIT ?"
    )
    return [tuple(r) for r in conn.execute(sql, (limit,))]


def customer_summary(conn, customer_id: int):
    sql = load_query("customer_ltv") + " HAVING customer_id = ?"
    row = conn.execute(sql, (customer_id,)).fetchone()
    return tuple(row) if row else None
