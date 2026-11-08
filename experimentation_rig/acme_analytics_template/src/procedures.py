"""Multi-step database operations. Each function runs inside a single transaction."""
from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def refresh_customer_ltv(conn) -> int:
    """Rebuild the customer_ltv table from captured payments. Returns the number of rows written."""
    try:
        conn.execute("DELETE FROM customer_ltv")
        conn.execute(
            "INSERT INTO customer_ltv (customer_id, order_count, lifetime_value, refreshed_at) "
            "SELECT o.customer_id, COUNT(*), "
            "ROUND(COALESCE((SELECT SUM(p.amount) FROM payments p "
            "                WHERE p.status = 'captured' AND p.order_id IN "
            "                (SELECT order_id FROM orders WHERE customer_id = o.customer_id)), 0), 2), ? "
            "FROM orders o GROUP BY o.customer_id",
            (_now(),),
        )
        count = conn.execute("SELECT COUNT(*) FROM customer_ltv").fetchone()[0]
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise


def set_customer_status(conn, customer_id: int, status: str) -> None:
    """Change a customer's status."""
    try:
        conn.execute("UPDATE customers SET status = ? WHERE customer_id = ?", (status, customer_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
