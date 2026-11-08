"""Experiment 2 data: best customers per region, flag slipping.

A small cast of ordinary-looking customers is given designed spending so that each planted problem changes the
answer. Natural customers stay far below the cast, so top-3 results are determined by the design.
Also holds the oracle that produces the expected output (stored in truth.db).
"""
from __future__ import annotations

import datetime as dt
import random
import re
import sqlite3

from . import common, seed
from .seed import D, END, PARENT, REGIONS, Order, cents_text, line_cents, top_of

AS_OF = D.fromisoformat(common.AS_OF)
CUR_START = AS_OF - dt.timedelta(days=89)          # 2025-04-02
PRIOR_END = AS_OF - dt.timedelta(days=90)          # 2025-04-01 (boundary day belongs to the prior window)
PRIOR_START = AS_OF - dt.timedelta(days=179)       # 2025-01-02
TOP_NAME = {r[0]: r[1] for r in REGIONS}
INVISIBLE = re.compile("[\u00a0\u200b\u200c\u200d\u2060\ufeff\t\r\n ]")


def person_key(email: str) -> str:
    return INVISIBLE.sub("", email).lower()


def d(m, day):
    return D(2025, m, day)


def _lines(w, rng, total):
    """Split a total into 4 positive lines that sum exactly to it."""
    parts, left = [], total
    for _ in range(3):
        part = max(100, int(total * rng.uniform(0.08, 0.3)))
        parts.append(part)
        left -= part
    assert left > 0
    parts.append(left)
    return [[rng.choice(w.regular_ids), 1, p, None] for p in parts]


SCALE = 3  # designed customers spend 3x the nominal amounts so they clear every natural customer


def cast_order(w, rng, c, date, total, *, status="completed", source=None, pay="split", refund=0,
               refund_style="int", date_style=None):
    total *= SCALE
    refund *= SCALE
    o = Order(c, date, source or "web", status, _lines(w, rng, total), "cast")
    o.cast = True
    if source == "eu_legacy":
        o.currency = "EUR"
    if date_style:
        o.date_style = date_style
    ts = seed.ts
    if pay == "split":
        first = total * 6 // 10
        o.payments.append([first, "captured", ts(date, rng)])
        o.payments.append([total - first, "captured", ts(date + dt.timedelta(days=2), rng)])
    elif pay == "single":
        o.payments.append([total, "captured", ts(date, rng)])
    elif pay == "failed_only":
        o.payments.append([total, "failed", ts(date, rng)])
    if refund:
        o.refunds.append(dict(cents=refund, date=date + dt.timedelta(days=9), style=refund_style))
    w.orders.append(o)
    c.orders.append(o)
    return o


def _strip_window(w, c, since=PRIOR_START):
    gone = [o for o in c.orders if o.date >= since]
    for o in gone:
        c.orders.remove(o)
        w.orders.remove(o)


def pre_id(w, seed_value):
    rng = random.Random(seed_value + 3)
    base = [c for c in w.customers if c.tag is None and c.status == "active" and c.region_id]
    by_top = {t: [c for c in base if top_of(c.region_id, PARENT) == t] for t in (1, 2, 3, 4)}
    for t in by_top:
        rng.shuffle(by_top[t])
    nulls = [c for c in w.customers if c.tag == "null_region"]
    used = set()

    def pick(top, region=None):
        c = by_top[top].pop()
        if region:
            c.region_id = region
        c.tag = "cast"
        _strip_window(w, c)
        return c

    cast = {}

    def orders(c, spec, **kw):
        for date, total in spec:
            cast_order(w, rng, c, date, total, **kw)

    # ---------------- North America
    na1 = pick(1, 15)
    orders(na1, [(d(4, 9), 240000), (d(4, 27), 240000), (d(5, 15), 240000), (d(6, 12), 240000)])
    orders(na1, [(d(1, 14), 400000), (d(2, 3), 400000), (d(2, 26), 400000), (d(4, 1), 300000)])
    # duplicate person: one dup group (type A, two records) moved to North America
    groups = {}
    for c in w.customers:
        if c.tag in ("dup_orig", "dup_copy"):
            groups.setdefault(c.group if c.tag == "dup_copy" else c.group, []).append(c)
    gid = next(g for g, m in sorted(groups.items()) if len(m) == 2 and m[0].kind == "A")
    na4a, na4b = sorted(groups[gid], key=lambda c: c.tag != "dup_orig")
    for c in (na4a, na4b):
        c.region_id = 16
        c.status = "active"
        _strip_window(w, c)
    orders(na4a, [(d(4, 12), 190000), (d(5, 20), 190000), (d(2, 11), 200000)])
    orders(na4b, [(d(4, 30), 145000), (d(6, 2), 145000), (d(3, 5), 150000)])
    na2 = pick(1, 17)
    na2.created_at = "2025-03-28 10:12:00"
    orders(na2, [(d(4, 15), 250000), (d(6, 20), 250000)])
    o = cast_order(w, rng, na2, d(5, 25), 250000, refund=120000, refund_style="ord")
    cast.update(NA1=na1, NA2=na2, NA4A=na4a, NA4B=na4b)

    # ---------------- Europe
    eu2 = pick(2, 21)
    orders(eu2, [(d(4, 8), 170000), (d(5, 2), 170000)])
    cast_order(w, rng, eu2, d(5, 20), 180000, date_style="mdy")
    orders(eu2, [(d(1, 20), 250000), (d(3, 10), 250000)])
    # EU1: an eu_legacy customer whose orders are reshaped (dates are DD/MM/YYYY and ambiguous)
    eu_custs = [c for c in w.customers if c.tag == "eu_legacy"]
    eu1 = eu_custs[-1]
    mine = sorted(eu1.orders, key=lambda o: o.date)
    assert len(mine) == 4
    plan = [(d(2, 4), 210000), (d(2, 9), 150000), (d(5, 3), 280000), (d(5, 7), 190000)]
    for o, (date, total) in zip(mine, plan):
        total *= SCALE
        o.date = date
        o.status = "completed"
        o.items = _lines(w, rng, total)
        o.payments = [[total, "captured", seed.ts(date, rng)]]
        o.refunds = []
        o.cast = True
    eu1.tag = "cast"
    eu3 = pick(2, 24)
    orders(eu3, [(d(4, 18), 150000), (d(5, 11), 150000), (d(6, 8), 100000), (d(2, 2), 300000)])
    cast_order(w, rng, eu3, d(5, 30), 250000, status="CANCELED")
    eu4 = pick(2, 25)
    orders(eu4, [(d(4, 22), 200000), (d(6, 14), 200000), (d(1, 30), 220000), (d(3, 20), 230000)])
    cast.update(EU1=eu1, EU2=eu2, EU3=eu3, EU4=eu4)

    # ---------------- Asia Pacific
    ap1 = pick(3, 26)
    orders(ap1, [(d(4, 11), 300000), (d(5, 26), 300000), (d(1, 19), 325000), (d(3, 21), 325000)])
    cast_order(w, rng, ap1, d(6, 3), 150000, status="canceled")
    ap2 = pick(3, 28)
    orders(ap2, [(d(4, 20), 275000), (d(6, 10), 275000), (d(2, 25), 500000)])
    ap3 = pick(3, 30)
    orders(ap3, [(d(5, 5), 210000), (d(6, 18), 210000), (d(2, 12), 210000), (d(3, 14), 210000)])
    ap4 = pick(3, 11)
    orders(ap4, [(d(4, 14), 210000), (d(6, 22), 210000), (d(3, 1), 600000)])
    cast.update(AP1=ap1, AP2=ap2, AP3=ap3, AP4=ap4)

    # ---------------- Latin America
    la1 = pick(4, 32)
    orders(la1, [(d(4, 16), 240000), (d(6, 5), 240000), (d(2, 8), 400000)])
    la2 = pick(4, 33)
    orders(la2, [(d(5, 9), 400000), (d(2, 14), 450000)])
    la3 = pick(4, 32)
    orders(la3, [(d(4, 25), 160000), (d(6, 15), 160000), (d(3, 3), 300000)])
    cast_order(w, rng, la3, d(5, 12), 200000, status="Cancelled")
    la4 = pick(4, 33)
    orders(la4, [(d(5, 21), 250000), (d(3, 18), 100000)])
    cast.update(LA1=la1, LA2=la2, LA3=la3, LA4=la4)

    # L2-11: an order exactly on the 90-day prior/current boundary (PRIOR_END = AS_OF - 90 days)
    cast_order(w, rng, ap2, PRIOR_END, 50000, pay="single")

    # ---------------- Unassigned (NULL region)
    u1, u2, u3, u4 = nulls[:4]
    for c in (u1, u2, u3, u4):
        c.tag = "cast"
        _strip_window(w, c, since=D(2024, 11, 21))
        c.status = "active"
    cast_order(w, rng, u1, d(5, 6), 120000, pay="single")
    cast_order(w, rng, u1, d(2, 7), 90000, pay="single")
    cast_order(w, rng, u4, d(6, 9), 40000, pay="single")
    cast_order(w, rng, u3, d(5, 14), 15000, pay="failed_only", refund=15000)
    cast_order(w, rng, u2, d(4, 29), 30000, pay="failed_only", refund=30000)
    cast.update(U1=u1, U2=u2, U3=u3, U4=u4)
    w.cast = cast


# ----------------------------------------------------------------------------- post-id plants

def post_id(w, seed_value):
    rng = random.Random(seed_value + 4)
    P = w.planter
    P.counts["L2-06"] = P.counts.get("L2-06", 0) + 1  # eu2's explicit mdy cast order
    used = P.used            # order ids already planted (shared with experiment 1)
    ref_used: set = set()    # refund ids (a separate id space)

    def choose(pool, k, tag, taken=None):
        taken = used if taken is None else taken
        cand = pool[:]
        rng.shuffle(cand)
        out = []
        for o in cand:
            key = o.id if hasattr(o, "id") else o["id"]
            if len(out) == k:
                break
            if key % 100 != 0 and key not in taken and key - 1 not in taken and key + 1 not in taken:
                taken.add(key)
                out.append(o)
        assert len(out) == k, tag
        P.counts[tag] = P.counts.get(tag, 0) + k
        return out

    natural = [o for o in w.orders if not o.cast and o.cust.tag is None]
    # L2-06: slash dates in month/day/year order on a few non-eu rows (one more sits on a cast order)
    pool = [o for o in natural if o.source in ("web", "mobile", "marketplace") and o.status == "completed"]
    for o in choose(pool, 39, "L2-06"):
        o.date_style = "mdy"
        o.date_text = o.date.strftime("%m/%d/%Y")
    # L2-07: status spelling variants (3 more on cast orders)
    canc = [o for o in natural if o.status == "cancelled"]
    for k, o in enumerate(choose(canc, 9, "L2-07")):
        o.status = ["Cancelled", "CANCELED", "canceled"][k % 3]
    P.counts["L2-07"] += 3
    # L2-02: refunds that a plain join misses
    refs = [dict(id=r["id"], r=r) for _, oid, r in w.refund_rows if not r["order"].cast]
    na2_ref = [r for _, oid, r in w.refund_rows if r["style"] == "ord"]
    P.counts["L2-02"] = len(na2_ref)
    ref_used.update(r["id"] for r in na2_ref)
    for item in choose(refs, 61, "L2-02", ref_used):
        item["r"]["style"] = "ord"
    for item in choose(refs, 6, "L2-02", ref_used):
        item["r"]["style"] = "missing"
    w.truth_writers = getattr(w, "truth_writers", [])
    result = oracle(w)
    w.exp2_result = result
    cast_people = {min(c2.id for c2 in w.customers if person_key(c2.email) == person_key(c.email))
                   for c in w.cast.values()}
    strangers = [r for r in result["rows"] if r["customer_id"] not in cast_people]
    assert not strangers, f"natural customers reached a top-3 slot: {strangers[:3]}"
    w.truth_writers.append(lambda conn: _write_truth(conn, w, result))


# ----------------------------------------------------------------------------- oracle

def oracle(w):
    """Expected output of best_customers_by_region for AS_OF, computed from the in-memory world."""
    groups = {}
    for c in w.customers:
        groups.setdefault(person_key(c.email), []).append(c)
    person_of = {}
    for members in groups.values():
        pid = min(m.id for m in members)
        for m in members:
            person_of[m.id] = pid
    by_id = {c.id: c for c in w.customers}
    net = {}
    prior = {}
    active = set()
    for o in w.orders:
        if o.status.strip().lower() in ("cancelled", "canceled"):
            continue
        if CUR_START <= o.date <= AS_OF:
            bucket = net
            active.add(person_of[o.cust.id])
        elif PRIOR_START <= o.date <= PRIOR_END:
            bucket = prior
        else:
            continue
        cents = sum(p[0] for p in o.payments if p[1] == "captured") - sum(r["cents"] for r in o.refunds
                                                                           if r["style"] != "missing")
        pid = person_of[o.cust.id]
        bucket[pid] = bucket.get(pid, 0) + cents
    by_group = {}
    for pid in active:
        rep = by_id[pid]
        group = TOP_NAME[top_of(rep.region_id, PARENT)] if rep.region_id else "Unassigned"
        by_group.setdefault(group, []).append(pid)
    rows = []
    candidates = {}
    for group, pids in by_group.items():
        for pid in pids:
            candidates[pid] = dict(customer_id=pid, region=group, net=net.get(pid, 0), prior=prior.get(pid, 0))
        for pid in pids:
            rank = 1 + sum(1 for q in pids if net.get(q, 0) > net.get(pid, 0))
            if rank <= 3:
                n, p = net.get(pid, 0), prior.get(pid, 0)
                pct = round((n - p) * 100.0 / p, 2) if p > 0 else None
                rows.append(dict(region=group, customer_id=pid, rank=rank, net_cents=n, prior_cents=p,
                                 pct_change=pct, slipping=int(p > 0 and n * 10 <= p * 7)))
    rows.sort(key=lambda r: (r["region"], r["rank"], r["customer_id"]))
    return dict(rows=rows, candidates=candidates)


def _write_truth(conn, w, result):
    conn.executescript("""
        CREATE TABLE truth_exp2_rows (region TEXT, customer_id INTEGER, rank INTEGER, net_cents INTEGER,
                                      prior_cents INTEGER, pct_change REAL, slipping INTEGER);
        CREATE TABLE truth_exp2_net (customer_id INTEGER PRIMARY KEY, region TEXT, net_cents INTEGER, prior_cents INTEGER);
        CREATE TABLE truth_exp2_cast (role TEXT PRIMARY KEY, customer_id INTEGER);
    """)
    conn.executemany("INSERT INTO truth_exp2_rows VALUES (?,?,?,?,?,?,?)",
                     [(r["region"], r["customer_id"], r["rank"], r["net_cents"], r["prior_cents"], r["pct_change"],
                       r["slipping"]) for r in result["rows"]])
    conn.executemany("INSERT INTO truth_exp2_net VALUES (?,?,?,?)",
                     [(c["customer_id"], c["region"], c["net"], c["prior"]) for c in result["candidates"].values()])
    person = {}
    for c in w.customers:
        person.setdefault(person_key(c.email), []).append(c.id)
    conn.executemany("INSERT INTO truth_exp2_cast VALUES (?,?)",
                     [(role, min(person[person_key(c.email)])) for role, c in sorted(w.cast.items())])


seed.sys_modules_hooks.pre_id.append(pre_id)
seed.sys_modules_hooks.post_id.append(post_id)
