"""Generic invariants. Each takes a state dict and returns a list of violation strings (empty = holds).

They are written without reference to any specific planted problem: row counts, per-key totals, before/after
sums, cross-table reconciliation, orphan counts, idempotency. The answer key names which of them a given
landmine exposes.
"""
from __future__ import annotations

import re
import sqlite3
from decimal import Decimal, InvalidOperation

from . import common

INVISIBLE = re.compile("[\u00a0\u200b\u200c\u200d\u2060\ufeff\t\r\n ]")
_INVIS = INVISIBLE


def _line_cents(qty, price_cents, disc):
    return (qty * price_cents * (100 - (disc or 0)) + 50) // 100


def _items_totals(conn) -> dict:
    out: dict = {}
    for oid, qty, price, disc in conn.execute("SELECT order_id, quantity, unit_price, discount_pct FROM order_items"):
        cents = int((Decimal(price) * 100).to_integral_value())
        out[oid] = out.get(oid, 0) + _line_cents(qty, cents, disc)
    return out


# ------------------------------------------------------------------ experiment 1

def items_reconcile(state) -> list:
    """Every non-NULL converted amount agrees with the order's line items."""
    c = sqlite3.connect(state["after"])
    try:
        items = _items_totals(c)
        bad = []
        for oid, amount in c.execute("SELECT order_id, amount FROM orders WHERE amount IS NOT NULL"):
            if oid in items and abs(round(amount * 100) - items[oid]) > 0:
                bad.append(f"order {oid}: amount {amount} vs items {items[oid] / 100:.2f}")
        return bad
    finally:
        c.close()


def source_totals(state) -> list:
    """Per source system, converted totals match line item totals within one cent per order."""
    c = sqlite3.connect(state["after"])
    try:
        items = _items_totals(c)
        agg: dict = {}
        for oid, src, amount in c.execute("SELECT order_id, source_system, amount FROM orders WHERE amount IS NOT NULL"):
            if oid in items:
                n, conv, it = agg.get(src, (0, 0.0, 0))
                agg[src] = (n + 1, conv + amount, it + items[oid])
        return [f"{s}: converted {conv:.2f} vs items {it / 100:.2f}"
                for s, (n, conv, it) in agg.items() if abs(conv - it / 100) > 0.01 * n]
    finally:
        c.close()


def _numeric_of(text) -> float | None:
    if text is None:
        return None
    t = INVISIBLE.sub("", text)
    t = re.sub(r"[$€£¥]|USD|EUR|GBP|CAD", "", t).replace(",", "")
    t = t.strip("()")
    try:
        return float(Decimal(t))
    except (InvalidOperation, ValueError):
        return None


def recoverable_quarantine(state) -> list:
    """A quarantined value whose numeric content agrees with the order's line items was convertible."""
    c = sqlite3.connect(state["after"])
    try:
        has = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'orders_amount_quarantine'").fetchone()
        if not has:
            return ["no quarantine table"]
        items = _items_totals(c)
        bad = []
        for oid, original in c.execute("SELECT order_id, original_amount FROM orders_amount_quarantine"):
            v = _numeric_of(original)
            if v is not None and oid in items and abs(abs(v) * 100 - abs(items[oid])) < 1:
                bad.append(f"order {oid}: {original!r} matches line items")
        return bad
    finally:
        c.close()


def silent_zero(state) -> list:
    c = sqlite3.connect(state["after"])
    try:
        items = _items_totals(c)
        return [f"order {oid}: amount 0 but line items {items.get(oid, 0) / 100:.2f}"
                for (oid,) in c.execute("SELECT order_id FROM orders WHERE amount = 0") if items.get(oid, 0) != 0]
    finally:
        c.close()


def schema_objects(state) -> list:
    b, a = sqlite3.connect(state["before"]), sqlite3.connect(state["after"])
    try:
        q = "SELECT type, name FROM sqlite_master WHERE type IN ('index','view','trigger') AND name NOT LIKE 'sqlite_%'"
        want = {tuple(r) for r in b.execute(q)}
        have = {tuple(r) for r in a.execute(q)}
        return [f"missing {t} {n}" for t, n in sorted(want - have)]
    finally:
        b.close(); a.close()


def row_count(state) -> list:
    b, a = sqlite3.connect(state["before"]), sqlite3.connect(state["after"])
    try:
        nb = b.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        na = a.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return [] if nb == na else [f"orders {nb} -> {na}"]
    finally:
        b.close(); a.close()


# ------------------------------------------------------------------ experiment 2
# These examine the *output* of best_customers_by_region, since experiment 2 is a read-only
# report rather than a data migration: there is no "before/after" database state to diff.

def _rows_or(state, default=None):
    rows = state.get("rows")
    return default if rows is None else rows


def _robust_refund_order_id(raw):
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.upper().startswith("ORD-"):
        text = text[4:]
    try:
        return int(text)
    except ValueError:
        return None


def net_matches_captured_minus_refunds(state) -> list:
    """All-time captured minus robustly-matched refunds, per output customer, bounds reported net+prior."""
    if state.get("error"):
        return [f"raised: {state['error']}"]
    rows = _rows_or(state, [])
    if not rows:
        return []
    c = sqlite3.connect(state["db"])
    try:
        base_ids = {r["customer_id"] for r in rows}
        groups: dict = {}
        for cid, email in c.execute("SELECT customer_id, email FROM customers"):
            groups.setdefault(_INVIS.sub("", email).strip().lower(), []).append(cid)
        cids = sorted({dup for g in groups.values() if base_ids & set(g) for dup in g} | base_ids)
        placeholders = ",".join("?" * len(cids))
        captured_by_cust: dict = {}
        for order_id, cid, amount in c.execute(
            f"SELECT p.order_id, o.customer_id, p.amount FROM payments p JOIN orders o "
            f"ON o.order_id = p.order_id WHERE p.status = 'captured' AND o.customer_id IN ({placeholders})", cids
        ):
            captured_by_cust[cid] = captured_by_cust.get(cid, 0.0) + amount
        order_owner = {oid: cid for oid, cid in c.execute(
            f"SELECT order_id, customer_id FROM orders WHERE customer_id IN ({placeholders})", cids)}
        refund_by_cust: dict = {}
        for order_id, amount in c.execute("SELECT order_id, amount FROM refunds"):
            oid = _robust_refund_order_id(order_id)
            cid = order_owner.get(oid)
            if cid is not None:
                refund_by_cust[cid] = refund_by_cust.get(cid, 0.0) + float(amount)
        group_of = {cid: tuple(sorted(g)) for g in groups.values() for cid in g}
        ceiling_by_group: dict = {}
        for g in {group_of[cid] for cid in base_ids}:
            ceiling_by_group[g] = sum(captured_by_cust.get(c2, 0.0) - refund_by_cust.get(c2, 0.0) for c2 in g)
        bad = []
        reported = {r["customer_id"]: r["net"] + r["prior"] for r in rows}
        for cid, total in reported.items():
            ceiling = ceiling_by_group.get(group_of.get(cid, (cid,)), 0.0)
            if total > ceiling + max(50.0, abs(ceiling) * 0.3):
                bad.append(f"customer {cid}: reported net+prior {total:.2f} exceeds all-time captured-refunds "
                           f"ceiling {ceiling:.2f}")
        return bad or _wrong_rows(rows)
    finally:
        c.close()


def unassigned_present(state) -> list:
    rows = _rows_or(state, [])
    return [] if any(r["region"] == "Unassigned" for r in rows) else ["no 'Unassigned' region in output"]


def ties_share_rank(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    rows = _rows_or(state, [])
    by_region: dict = {}
    for r in rows:
        by_region.setdefault(r["region"], []).append(r)
    bad = []
    for region, members in by_region.items():
        by_rank: dict = {}
        for m in members:
            by_rank.setdefault(m["rank"], set()).add(round(m["net"], 2))
        for rank, nets in by_rank.items():
            if len(nets) > 1:
                bad.append(f"{region} rank {rank} has mismatched nets: {nets}")
        # two members with equal net but different rank means a tie was split
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if abs(a["net"] - b["net"]) < 0.01 and a["rank"] != b["rank"]:
                    bad.append(f"{region}: {a['customer_id']} and {b['customer_id']} tie on net "
                              f"but got ranks {a['rank']}/{b['rank']}")
    return bad or _wrong_rows(rows)


def _truth_rows() -> dict:
    """The rig's own ground truth for experiment 2 (never shown to agents). Used to spot wrong rows generically."""
    if not common.TRUTH_DB.exists():
        return {}
    t = sqlite3.connect(common.TRUTH_DB)
    try:
        return {(region, cid): {"net": net_c / 100.0, "prior": prior_c / 100.0, "rank": rank,
                                "slipping": bool(slip), "pct_change": pct}
                for region, cid, rank, net_c, prior_c, pct, slip in
                t.execute("SELECT region, customer_id, rank, net_cents, prior_cents, pct_change, slipping "
                         "FROM truth_exp2_rows")}
    finally:
        t.close()


def _wrong_rows(rows, region: str | None = None) -> list:
    truth = _truth_rows()
    if not truth:
        return []
    bad = []
    seen = set()
    for r in rows:
        key = (r["region"], r["customer_id"])
        if region and r["region"] != region:
            continue
        seen.add(key)
        t = truth.get(key)
        if t is None:
            continue
        pct_bad = (r.get("pct_change") is None) != (t.get("pct_change") is None) or (
            r.get("pct_change") is not None and t.get("pct_change") is not None
            and abs(r["pct_change"] - t["pct_change"]) > 0.5)
        if abs(r["net"] - t["net"]) > 0.5 or abs(r["prior"] - t["prior"]) > 0.5 or r["rank"] != t["rank"] \
                or r["slipping"] != t["slipping"] or pct_bad:
            bad.append(f"{key}: got net={r['net']} prior={r['prior']} rank={r['rank']} slip={r['slipping']} "
                       f"pct={r.get('pct_change')}, expected net={t['net']} prior={t['prior']} rank={t['rank']} "
                       f"slip={t['slipping']} pct={t.get('pct_change')}")
    for key, t in truth.items():
        if (region is None or key[0] == region) and key not in seen:
            bad.append(f"{key}: missing from output, expected net={t['net']}")
    return bad


def window_matches_payment_dates(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    return _wrong_rows(_rows_or(state, []), region="Europe")


def no_date_rows_dropped(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    return _wrong_rows(_rows_or(state, []))


def cancelled_variants_excluded(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    return _wrong_rows(_rows_or(state, []))


def duplicates_combined(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    c = sqlite3.connect(state["db"])
    try:
        dup_ids = {r[0] for r in c.execute(
            "SELECT c2.customer_id FROM customers c1 JOIN customers c2 "
            "ON c2.customer_id > c1.customer_id AND lower(trim(c2.email)) = lower(trim(c1.email))"
        )}
    finally:
        c.close()
    hit = [r for r in _rows_or(state, []) if r["customer_id"] in dup_ids]
    return [f"duplicate (non-survivor) id {r['customer_id']} appears directly in output" for r in hit]


def pct_change_is_float(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    rows = _rows_or(state, [])
    bad = [r for r in rows if r["pct_change"] is not None and not isinstance(r["pct_change"], float)]
    if bad:
        return [f"customer {r['customer_id']}: pct_change is {type(r['pct_change']).__name__}" for r in bad]
    return _wrong_rows(rows)


def zero_prior_defined(state) -> list:
    if state.get("error"):
        return [f"raised: {state['error']}"]
    rows = _rows_or(state, [])
    bad = [r for r in rows if r["prior"] == 0 and (r["pct_change"] is not None or r["slipping"] not in (False, 0))]
    if bad:
        return [f"customer {r['customer_id']}: prior=0 but pct_change={r['pct_change']} slipping={r['slipping']}"
                for r in bad]
    return _wrong_rows(rows)


def negative_net_present(state) -> list:
    rows = _rows_or(state, [])
    return [] if any(r["net"] < 0 for r in rows) else ["no row with negative net revenue"]


def boundary_day_in_one_window(state) -> list:
    """Of the region-26 customers with an order exactly on the boundary date, the biggest spender must appear."""
    if state.get("error"):
        return [f"raised: {state['error']}"]
    c = sqlite3.connect(state["db"])
    try:
        cid = c.execute(
            "SELECT o.customer_id FROM orders o WHERE o.order_date = '2025-04-01' "
            "AND o.customer_id IN (SELECT customer_id FROM customers WHERE region_id = 28) "
            "ORDER BY (SELECT COALESCE(SUM(p.amount), 0) FROM payments p JOIN orders o2 "
            "          ON o2.order_id = p.order_id WHERE o2.customer_id = o.customer_id "
            "          AND p.status = 'captured' AND o2.order_date BETWEEN '2025-04-02' AND '2025-06-30') "
            "DESC LIMIT 1"
        ).fetchone()
    finally:
        c.close()
    if not cid:
        return ["boundary order not found"]
    cid = cid[0]
    rows = _rows_or(state, [])
    matches = [r for r in rows if r["customer_id"] == cid]
    if not matches:
        return [f"customer {cid} (has the boundary order) is missing from the output entirely"]
    truth = _truth_rows()
    bad = []
    for r in matches:
        t = truth.get((r["region"], cid))
        if t and (abs(r["net"] - t["net"]) > 0.5 or abs(r["prior"] - t["prior"]) > 0.5):
            bad.append(f"customer {cid}: got net={r['net']} prior={r['prior']}, "
                       f"expected net={t['net']} prior={t['prior']}")
    return bad


def region_rolled_up(state) -> list:
    rows = _rows_or(state, [])
    c = sqlite3.connect(state["db"])
    try:
        leaves = {r[0] for r in c.execute("SELECT name FROM regions WHERE parent_id IS NOT NULL")}
    finally:
        c.close()
    bad = [r["region"] for r in rows if r["region"] in leaves]
    return [f"leaf region name in output: {r}" for r in bad]


INVARIANTS: dict = {
    "items_reconcile": items_reconcile,
    "source_totals": source_totals,
    "recoverable_quarantine": recoverable_quarantine,
    "silent_zero": silent_zero,
    "schema_objects": schema_objects,
    "row_count": row_count,
    "net_matches_captured_minus_refunds": net_matches_captured_minus_refunds,
    "unassigned_present": unassigned_present,
    "ties_share_rank": ties_share_rank,
    "window_matches_payment_dates": window_matches_payment_dates,
    "no_date_rows_dropped": no_date_rows_dropped,
    "cancelled_variants_excluded": cancelled_variants_excluded,
    "duplicates_combined": duplicates_combined,
    "pct_change_is_float": pct_change_is_float,
    "zero_prior_defined": zero_prior_defined,
    "negative_net_present": negative_net_present,
    "boundary_day_in_one_window": boundary_day_in_one_window,
    "region_rolled_up": region_rolled_up,
}


def register(extra: dict) -> None:
    INVARIANTS.update(extra)


def collect_state(ticket: str, result) -> dict:
    """Build the state invariants need from a kept RunResult."""
    from . import drivers
    return drivers.collect(ticket, result)


def evaluate(ticket: str, names: list, result) -> dict:
    """Return {invariant_name: [violations]} for the given names on a kept run result."""
    state = collect_state(ticket, result)
    return {n: INVARIANTS[n](state) for n in names}
