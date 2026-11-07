"""Reporting functions. SQL text lives in queries/*.sql."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parents[1] / "queries"
_INVISIBLE = re.compile("[\u00a0\u200b\u200c\u200d\u2060\ufeff\t\r\n ]")
_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CANCELLED = {"cancelled", "canceled"}


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


# --------------------------------------------------------------------------- best_customers_by_region

def _normalize_email(email: str) -> str:
    return _INVISIBLE.sub("", email).strip().lower()


def _safe_date(y, m, dd):
    try:
        return date(y, m, dd)
    except ValueError:
        return None


def _parse_order_date(raw: str, payment_dates: list):
    raw = (raw or "").strip()
    if _ISO.match(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    m = _SLASH.match(raw)
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    cand_mdy = _safe_date(y, a, b)  # first component is the month
    cand_dmy = _safe_date(y, b, a)  # first component is the day
    if cand_mdy and not cand_dmy:
        return cand_mdy
    if cand_dmy and not cand_mdy:
        return cand_dmy
    if not cand_mdy and not cand_dmy:
        return None
    if payment_dates:
        pivot = min(payment_dates)
        return cand_mdy if abs((cand_mdy - pivot).days) <= abs((cand_dmy - pivot).days) else cand_dmy
    return cand_mdy


def _refund_order_id(raw):
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.upper().startswith("ORD-"):
        text = text[4:]
    try:
        return int(text)
    except ValueError:
        return None


def _region_rollup(conn) -> dict:
    parent = {}
    name = {}
    for rid, rname, pid in conn.execute("SELECT region_id, name, parent_id FROM regions"):
        parent[rid] = pid
        name[rid] = rname
    top = {}
    for rid in parent:
        cur = rid
        seen = set()
        while parent.get(cur) is not None and cur not in seen:
            seen.add(cur)
            cur = parent[cur]
        top[rid] = name[cur]
    return top


def best_customers_by_region(conn, as_of: str):
    """Top 3 customers by net revenue in each region, with slip flags. See contracts/exp2.md."""
    as_of_date = date.fromisoformat(as_of)
    cur_start = as_of_date.fromordinal(as_of_date.toordinal() - 90)
    prior_end = as_of_date.fromordinal(as_of_date.toordinal() - 90)
    prior_start = as_of_date.fromordinal(as_of_date.toordinal() - 179)

    customers = conn.execute("SELECT customer_id, email, region_id FROM customers").fetchall()
    groups: dict = {}
    for cid, email, region_id in customers:
        groups.setdefault(_normalize_email(email), []).append((cid, region_id))
    person_of, person_region = {}, {}
    for members in groups.values():
        members.sort(key=lambda m: m[0])
        pid, region = members[0]
        for cid, _ in members:
            person_of[cid] = pid
        person_region[pid] = region

    top_name = _region_rollup(conn)

    orders = conn.execute(
        "SELECT order_id, customer_id, order_date, status FROM orders"
    ).fetchall()
    payments_by_order: dict = {}
    for order_id, amount, status in conn.execute("SELECT order_id, amount, status FROM payments"):
        payments_by_order.setdefault(order_id, []).append((amount, status))
    paid_dates_by_order: dict = {}
    for order_id, paid_at in conn.execute("SELECT order_id, paid_at FROM payments"):
        paid_dates_by_order.setdefault(order_id, []).append(date.fromisoformat(paid_at[:10]))
    refunds_by_order: dict = {}
    for order_id, amount in conn.execute("SELECT order_id, amount FROM refunds"):
        oid = _refund_order_id(order_id)
        if oid is not None:
            refunds_by_order.setdefault(oid, 0.0)
            refunds_by_order[oid] += float(amount)

    net, prior = {}, {}
    active = set()
    for order_id, customer_id, order_date, status in orders:
        if (status or "").strip().lower() in _CANCELLED:
            continue
        parsed = _parse_order_date(order_date, paid_dates_by_order.get(order_id, []))
        if parsed is None:
            continue
        if cur_start <= parsed <= as_of_date:
            bucket = net
        elif prior_start <= parsed <= prior_end:
            bucket = prior
        else:
            continue
        captured = sum(a for a, st in payments_by_order.get(order_id, []) if st == "captured")
        revenue = captured - refunds_by_order.get(order_id, 0.0)
        pid = person_of[customer_id]
        bucket[pid] = round(bucket.get(pid, 0.0) + revenue, 2)
        if bucket is net:
            active.add(pid)

    by_region: dict = {}
    for pid in active:
        region_id = person_region.get(pid)
        region_name = top_name.get(region_id, "Unassigned") if region_id is not None else "Unassigned"
        by_region.setdefault(region_name, []).append(pid)

    rows = []
    for region, pids in by_region.items():
        for pid in pids:
            n = net.get(pid, 0.0)
            rank = 1 + sum(1 for other in pids if net.get(other, 0.0) > n)
            if rank > 3:
                continue
            p = prior.get(pid, 0.0)
            pct_change = round((n - p) * 100.0 / p, 2) if p > 0 else None
            slipping = bool(p > 0 and n <= p * 0.7)
            rows.append({"region": region, "customer_id": pid, "rank": rank, "net": round(n, 2),
                        "prior": round(p, 2), "pct_change": pct_change, "slipping": slipping})
    rows.sort(key=lambda r: (r["region"], r["rank"], r["customer_id"]))
    return rows
