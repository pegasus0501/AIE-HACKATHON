"""Deterministic seeder for data/acme.db and data/truth.db (SEED=42).

Pipeline (all in memory, ids assigned late so planted rows land at scattered ids):
  customers -> orders (+items, payments, refunds) -> experiment-2 cast -> id assignment
  -> experiment-1 text plants -> write acme.db -> write truth.db
"""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import common
from .common import ACME_DB, DATA_DIR, TEMPLATE_DIR, TRUTH_DB

D = dt.date
START = D(2023, 1, 1)
END = D(2025, 6, 30)
MIG_DIR = TEMPLATE_DIR / "migrations"

FIRST = ("James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William Barbara Richard Susan "
         "Joseph Jessica Thomas Sarah Charles Karen Daniel Nancy Matthew Lisa Anthony Betty Mark Margaret Paul "
         "Sandra Steven Ashley Andrew Kimberly Kenneth Emily Joshua Donna Kevin Michelle Brian Carol George "
         "Amanda Edward Melissa Ronald Deborah Timothy Stephanie Jason Rebecca Jeffrey Laura Ryan Sharon Jacob "
         "Cynthia Gary Kathleen Nicholas Amy").split()
LAST = ("Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Gonzalez "
        "Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez Clark "
        "Ramirez Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green Adams "
        "Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips Evans Turner Diaz Parker "
        "Cruz Edwards Collins Reyes Stewart Morris").split()
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "example.com", "mail.net", "proton.me"]
CATEGORIES = ["Home", "Kitchen", "Outdoor", "Electronics", "Fitness", "Office", "Toys", "Beauty"]
WORDS = ["Classic", "Deluxe", "Compact", "Pro", "Eco", "Smart", "Lite", "Prime", "Urban", "Alpine", "Nova", "Zen"]
NOUNS = ["Lamp", "Kettle", "Tent", "Speaker", "Mat", "Chair", "Puzzle", "Serum", "Blender", "Backpack", "Monitor",
         "Dumbbell", "Notebook", "Robot", "Cleanser", "Grill", "Headset", "Bottle", "Desk", "Console"]
CHEAP = [("Sticker pack", 120), ("Pin set", 150), ("Keychain", 250), ("Bookmark", 310), ("Magnet", 99)]

# (region_id, name, parent_id)
REGIONS = [
    (1, "North America", None), (2, "Europe", None), (3, "Asia Pacific", None), (4, "Latin America", None),
    (5, "United States East", 1), (6, "United States West", 1), (7, "Canada", 1),
    (8, "United Kingdom", 2), (9, "Germany", 2), (10, "France", 2),
    (11, "Japan", 3), (12, "Australia", 3), (13, "India", 3), (14, "Brazil", 4),
    (15, "New York Metro", 5), (16, "New England", 5), (17, "California", 6), (18, "Pacific Northwest", 6),
    (19, "Ontario", 7), (20, "British Columbia", 7), (21, "London", 8), (22, "Scotland", 8),
    (23, "Bavaria", 9), (24, "Berlin", 9), (25, "Ile-de-France", 10), (26, "Tokyo", 11), (27, "Osaka", 11),
    (28, "Sydney", 12), (29, "Melbourne", 12), (30, "Mumbai", 13), (31, "Delhi", 13),
    (32, "Sao Paulo", 14), (33, "Rio de Janeiro", 14),
]
LEAVES = list(range(15, 34))
EU_LEAVES = [23, 24, 25]
CITY = {15: "New York", 16: "Boston", 17: "San Diego", 18: "Seattle", 19: "Toronto", 20: "Vancouver", 21: "London",
        22: "Glasgow", 23: "Munich", 24: "Berlin", 25: "Paris", 26: "Tokyo", 27: "Osaka", 28: "Sydney",
        29: "Melbourne", 30: "Mumbai", 31: "Delhi", 32: "Sao Paulo", 33: "Rio de Janeiro"}


def top_of(region_id, parent):
    while parent.get(region_id) is not None:
        region_id = parent[region_id]
    return region_id


PARENT = {r[0]: r[2] for r in REGIONS}


def cents_text(c: int) -> str:
    sign = "-" if c < 0 else ""
    c = abs(c)
    return f"{sign}{c // 100}.{c % 100:02d}"


def line_cents(qty, price, disc):
    return (qty * price * (100 - (disc or 0)) + 50) // 100


def iso(d: D) -> str:
    return d.isoformat()


def ts(d: D, rng, lo=8, hi=21) -> str:
    return f"{d.isoformat()} {rng.randint(lo, hi):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"


class Cust:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.id = None
        self.orders = []
        self.addresses = []
        self.tag = None
        self.max_date = END


class Order:
    def __init__(self, cust, date, source, status, items, kind="normal"):
        self.cust = cust
        self.date = date
        self.source = source
        self.status = status
        self.items = items  # list of [product_id, qty, price_cents, disc]
        self.kind = kind
        self.payments = []  # [cents, status, paid_at]
        self.refunds = []   # dicts
        self.currency = "USD"
        self.id = None
        self.amount_text = None
        self.tag = None
        self.cast = False
        self.date_text = None
        self.date_style = "dmy" if source == "eu_legacy" else "iso"

    @property
    def total(self):
        return sum(line_cents(it[1], it[2], it[3]) for it in self.items)


# --------------------------------------------------------------------------- build

class World:
    pass


def build_world(seed: int = common.SEED) -> World:
    rng = random.Random(seed)
    w = World()
    w.rng = rng
    w.regions = REGIONS
    _make_products(w)
    _make_customers(w)
    _make_orders(w)
    return w


def _make_products(w):
    rng = w.rng
    w.categories = [(i + 1, n) for i, n in enumerate(CATEGORIES)]
    prods = []
    pid = 1
    for _ in range(112):
        cat = rng.randint(1, len(CATEGORIES))
        price = int(min(20000, max(500, rng.lognormvariate(7.9, 0.75) * 1.0)))  # cents, ~$27 median
        price = price // 5 * 5 + 4 if rng.random() < 0.5 else price // 10 * 10 + 9
        name = f"{rng.choice(WORDS)} {rng.choice(NOUNS)}"
        prods.append([pid, f"SKU-{pid:04d}", name, cat, price])
        pid += 1
    for nm, price in CHEAP:
        prods.append([pid, f"SKU-{pid:04d}", nm, 6, price])
        pid += 1
    for k in range(6):  # premium items
        price = [49900, 64900, 74900, 89900, 59900, 79900][k]
        prods.append([pid, f"SKU-{pid:04d}", f"{rng.choice(WORDS)} {rng.choice(NOUNS)} X", 4, price])
        pid += 1
    w.products = prods
    w.cheap_ids = {price: p[0] for p in prods for nm, price in CHEAP if p[2] == nm}
    w.premium_ids = [p[0] for p in prods[-6:]]
    w.regular_ids = [p[0] for p in prods[:112]]
    w.price_of = {p[0]: p[4] for p in prods}


def _phone(rng, region):
    top = top_of(region, PARENT) if region else 1
    if top == 1:
        return f"+1-{rng.randint(201, 989)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
    if top == 2:
        return f"+{rng.choice([44, 49, 33])} {rng.randint(20, 99)} {rng.randint(1000000, 9999999)}"
    if top == 3:
        return f"+{rng.choice([81, 61, 91])}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
    return f"+55-{rng.randint(11, 99)}-{rng.randint(90000, 99999)}-{rng.randint(1000, 9999)}"


def _rand_date(rng, lo: D, hi: D) -> D:
    return lo + dt.timedelta(days=rng.randint(0, (hi - lo).days))


def _make_customers(w):
    rng = w.rng
    pairs = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(pairs)
    base_n = 1945
    custs = []
    used_emails = set()
    weights = {"NA": 40, "EU": 30, "AP": 20, "LA": 10}
    leaf_by_top = defaultdict(list)
    for r in LEAVES:
        leaf_by_top[top_of(r, PARENT)].append(r)
    top_choices = [1] * 40 + [2] * 30 + [3] * 20 + [4] * 10

    def mk(first, last, region, source, created=None, email=None, name=None):
        created = created or _rand_date(rng, D(2021, 1, 1), D(2025, 5, 31))
        upd = min(D(2025, 6, 20), created + dt.timedelta(days=rng.randint(0, 700)))
        email = email or f"{first}.{last}@{rng.choice(DOMAINS)}".lower()
        c = Cust(email=email, full_name=name or f"{first} {last}", region_id=region,
                 phone=None if rng.random() < 0.03 else _phone(rng, region),
                 status=rng.choices(["active", "inactive", "suspended"], [90, 8, 2])[0],
                 created_at=ts(created, rng, 0, 23), updated_at=ts(upd, rng, 0, 23),
                 legacy_id=None, source_system=source, created_d=created)
        if rng.random() < 0.25:
            c.legacy_id = f"LC{rng.randint(10000, 99999)}"
        return c

    for i in range(base_n):
        first, last = pairs[i]
        top = rng.choice(top_choices)
        region = rng.choice(leaf_by_top[top])
        if rng.random() < 0.06:
            region = PARENT[region]
        custs.append(mk(first, last, region, None))
    # sources: eu_legacy (22, Europe leaves), pos_v2 (14, NA/APAC), NULL region (28)
    idx = list(range(base_n))
    rng.shuffle(idx)
    eu_pool = [i for i in idx if top_of(custs[i].region_id, PARENT) == 2]
    na_ap = [i for i in idx if top_of(custs[i].region_id, PARENT) in (1, 3)]
    eu_ids, pos_ids = eu_pool[:22], na_ap[:14]
    for i in eu_ids:
        custs[i].source_system = "eu_legacy"
        custs[i].region_id = rng.choice(EU_LEAVES)
        custs[i].phone = f"+49 {rng.randint(20, 99)} {rng.randint(1000000, 9999999)}"
    for i in pos_ids:
        custs[i].source_system = "pos_v2"
    taken = set(eu_ids) | set(pos_ids)
    rest = [i for i in idx if i not in taken]
    for n, i in enumerate(rest):
        custs[i].source_system = rng.choices(["web", "mobile", "marketplace"], [55, 30, 15])[0]
    null_ids = [i for i in rest if custs[i].legacy_id is None][:28]
    for i in null_ids:
        custs[i].region_id = None
        custs[i].tag = "null_region"
        custs[i].max_date = D(2024, 11, 20)
    for i in eu_ids:
        custs[i].tag = "eu_legacy"
    for i in pos_ids:
        custs[i].tag = "pos_v2"
    base = custs[:base_n]
    eligible = [c for c in base if c.tag is None]
    rng.shuffle(eligible)

    # ---- experiment 3: namesakes (different people), plus-tag lookalikes, duplicates
    ei = 0
    for _ in range(12):
        o = eligible[ei]; ei += 1
        first, last = o.full_name.split(" ", 1)
        email = f"{first}.{last}.{rng.randint(10, 99)}@{rng.choice(DOMAINS)}".lower()
        region = rng.choice(LEAVES)
        n = mk(first, last, region, rng.choice(["web", "mobile"]), email=email, name=o.full_name)
        n.tag = "namesake"; n.partner = o; custs.append(n)
        o.tag = "namesake_orig"
    for _ in range(6):
        o = eligible[ei]; ei += 1
        local, dom = o.email.split("@")
        first = rng.choice(FIRST)
        n = mk(first, o.full_name.split(" ", 1)[1], o.region_id, o.source_system,
               email=f"{local}+promo@{dom}")
        n.tag = "plus_tag"; n.partner = o; custs.append(n)
        o.tag = "plus_tag_orig"
    dups = []
    kindsA = ["upper", "trail_space", "title", "lead_space", "trail_tab", "upper_name"]
    for g in range(16):
        o = eligible[ei]; ei += 1
        o.tag = "dup_orig"
        members = 2 if g != 4 else 3
        kind = "A" if g < 11 else "B"
        o.group = g
        for m in range(members - 1):
            local, dom = o.email.split("@")
            if kind == "A":
                v = kindsA[(g + m) % len(kindsA)]
                email = {"upper": o.email.upper(), "trail_space": o.email + " ", "title": o.email.title(),
                         "lead_space": " " + o.email, "trail_tab": o.email + "\t",
                         "upper_name": o.email.upper()}[v]
                name = o.full_name.upper() if v == "upper_name" else o.full_name
            else:
                v = ["zwsp_mid", "nbsp_end", "zwsp_at", "bom_start"][g % 4]
                email = {"zwsp_mid": local[:3] + "\u200b" + local[3:] + "@" + dom,
                         "nbsp_end": o.email + "\u00a0", "zwsp_at": local + "\u200b@" + dom,
                         "bom_start": "\ufeff" + o.email}[v]
                name = o.full_name
            created = _rand_date(rng, D(2021, 6, 1), D(2025, 4, 30))
            n = mk("x", "x", o.region_id, o.source_system, created=created, email=email, name=name)
            n.tag = "dup_copy"; n.group = g; n.kind = kind; n.partner = o
            n.phone = None if (g in (3, 12) and m == 0) else _phone(rng, o.region_id)
            n.updated_at = ts(D(2025, 5, 1) + dt.timedelta(days=rng.randint(0, 40)), rng, 0, 23)
            n.legacy_id = f"LC{rng.randint(10000, 99999)}" if rng.random() < 0.6 else None
            custs.append(n); dups.append(n)
        o.updated_at = ts(D(2024, rng.randint(1, 12), rng.randint(1, 28)), rng, 0, 23)
        o.kind = kind
    w.customers = custs
    # addresses
    for c in custs:
        region = c.region_id or rng.choice(LEAVES)
        city = CITY.get(region) or CITY[rng.choice(LEAVES)]
        base_upd = c.updated_at
        c.addresses.append(dict(line1=f"{rng.randint(1, 9999)} {rng.choice(NOUNS)} Street", city=city,
                                postal=f"{rng.randint(10000, 99999)}", primary=1, updated_at=base_upd))
        if rng.random() < 0.3:
            c.addresses.append(dict(line1=f"{rng.randint(1, 999)} {rng.choice(WORDS)} Avenue", city=city,
                                    postal=f"{rng.randint(10000, 99999)}", primary=0,
                                    updated_at=ts(_rand_date(rng, D(2022, 1, 1), D(2024, 12, 31)), rng, 0, 23)))
    w.dup_copies = dups


def _pick_items(w, rng, kind="normal", cheap_price=None):
    if kind == "cheap":
        return [[w.cheap_ids[cheap_price], 1, cheap_price, None]]
    n = rng.choices([1, 2, 3, 4, 5, 6], [20, 25, 22, 15, 10, 8])[0]
    items = []
    for k in range(n):
        if kind == "premium" and k == 0:
            pid = rng.choice(w.premium_ids)
            qty = rng.choice([1, 1, 2])
        else:
            pid = rng.choice(w.regular_ids) if rng.random() > 0.012 else rng.choice(w.premium_ids)
            qty = rng.choices([1, 2, 3], [70, 20, 10])[0]
        price = w.price_of[pid]
        if rng.random() < 0.15:
            price = price * 95 // 100
        disc = rng.choices([None, 5, 10, 15, 20], [70, 8, 10, 8, 4])[0]
        items.append([pid, qty, price, disc])
    return items


def _make_orders(w):
    rng = w.rng
    days = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    wt = []
    for d in days:
        month_factor = {11: 1.35, 12: 1.6, 1: 0.85, 2: 0.8}.get(d.month, 1.0)
        growth = 0.7 + 0.6 * ((d - START).days / len(days))
        wt.append(month_factor * growth * (1.15 if d.weekday() >= 5 else 1.0))
    cum = []
    s = 0.0
    for x in wt:
        s += x
        cum.append(s)

    def rand_day(lo=START, hi=END):
        while True:
            d = rng.choices(days, cum_weights=cum, k=1)[0]
            if lo <= d <= hi:
                return d

    # order counts per customer
    n_special = 90 + 60
    pool_total = 20000 - n_special - 14  # 14 adjustment orders added separately
    normal = [c for c in w.customers if c.tag not in ("eu_legacy", "pos_v2")]
    weights = []
    for c in normal:
        wgt = min(rng.paretovariate(1.5), 8.0)
        if rng.random() < 0.05:
            wgt = 0.0
        if c.tag == "null_region":
            wgt = 0.0
        if c.tag in ("dup_copy", "dup_orig"):
            wgt = max(wgt, 2.5)
        weights.append(wgt)
    tot = sum(weights)
    counts = [int(x / tot * pool_total) for x in weights]
    for i, c in enumerate(normal):
        if c.tag in ("dup_copy", "dup_orig") and counts[i] < 3:
            counts[i] = 3
        if c.tag == "null_region":
            counts[i] = rng.choice([0, 1, 2, 3])
    deficit = pool_total - sum(counts)
    order_idx = [i for i, c in enumerate(normal) if c.tag != "null_region" and weights[i] > 0]
    while deficit != 0:
        i = rng.choice(order_idx)
        if deficit > 0:
            counts[i] += 1; deficit -= 1
        elif counts[i] > 3:
            counts[i] -= 1; deficit += 1
    orders = []

    def new_order(c, d, source, kind="normal", cheap_price=None):
        items = _pick_items(w, rng, kind, cheap_price)
        status = rng.choices(["completed", "cancelled", "pending", "returned", "shipped"],
                             [84, 6, 3, 5, 2])[0]
        o = Order(c, d, source, status, items, kind)
        if source == "eu_legacy":
            o.currency = "EUR"
        elif source == "marketplace" and rng.random() < 0.3:
            o.currency = None
        # keep natural basket sizes bounded
        while o.total > 180000 and len(o.items) > 1:
            o.items.pop()
        orders.append(o)
        c.orders.append(o)
        return o

    for c, n in zip(normal, counts):
        lo = max(START, c.created_d)
        hi = c.max_date
        for _ in range(n):
            d = rand_day(lo, hi) if lo < hi else lo
            src = rng.choices(["web", "mobile", "marketplace"], [55, 30, 15])[0]
            if c.source_system in ("web", "mobile", "marketplace") and rng.random() < 0.7:
                src = c.source_system
            new_order(c, d, src)

    eu = [c for c in w.customers if c.tag == "eu_legacy"]
    pos = [c for c in w.customers if c.tag == "pos_v2"]
    eu_plan = [4] * 22
    eu_plan[0] += 1; eu_plan[1] += 1
    kinds_eu = ["cheap1.20", "cheap2.50", "cheap3.10", "cheap1.50"] + ["premium"] * 8
    k_i = 0
    for c, n in zip(eu, eu_plan):
        for _ in range(n):
            d = rand_day(D(2025, 1, 2), END) if rng.random() < 0.7 else rand_day(max(START, c.created_d), END)
            if k_i < len(kinds_eu):
                kd = kinds_eu[k_i]; k_i += 1
            else:
                kd = "normal"
            if kd.startswith("cheap"):
                o = new_order(c, d, "eu_legacy", "cheap", int(round(float(kd[5:]) * 100)))
                o.status = "completed"
            else:
                o = new_order(c, d, "eu_legacy", kd)
    pos_plan = [4] * 14
    for i in range(4):
        pos_plan[i] += 1
    for c, n in zip(pos, pos_plan):
        for _ in range(n):
            new_order(c, rand_day(max(START, c.created_d), END), "pos_v2")

    # adjustment orders (negative amounts)
    adj_pool = [c for c in normal if c.tag is None and c.orders]
    for k in range(14):
        c = rng.choice(adj_pool)
        cents = rng.choice([1000, 2500, 5000, 7500, 12000, 4550, 3025]) + rng.randint(0, 99)
        o = Order(c, rand_day(max(START, c.created_d), END), rng.choice(["web", "mobile"]), "adjustment",
                  [[rng.choice(w.regular_ids), 1, -cents, None]], "adjustment")
        orders.append(o); c.orders.append(o)

    # payments / refunds
    for o in orders:
        tot = o.total
        base_ts = ts(o.date, rng)
        if o.status == "adjustment":
            continue
        if o.status == "pending":
            o.payments.append([tot, "pending", base_ts])
            continue
        r = rng.random()
        if r < 0.12:
            first = tot * 6 // 10
            o.payments.append([first, "captured", base_ts])
            o.payments.append([tot - first, "captured", ts(o.date + dt.timedelta(days=rng.randint(1, 5)), rng)])
        elif r < 0.21:
            o.payments.append([tot, "failed", ts(o.date, rng, 6, 7)])
            o.payments.append([tot, "captured", base_ts])
        else:
            o.payments.append([tot, "captured", base_ts])
        rd = o.date + dt.timedelta(days=rng.randint(3, 30))
        if o.status == "returned":
            o.refunds.append(dict(cents=tot, date=rd, style="int"))
        elif o.status == "cancelled" and rng.random() < 0.5:
            o.refunds.append(dict(cents=tot, date=rd, style="int"))
        elif o.status in ("completed", "shipped") and rng.random() < 0.08:
            o.refunds.append(dict(cents=max(100, tot * rng.randint(10, 80) // 100), date=rd, style="int"))
    w.orders = orders
    w.rand_day = rand_day
    w.new_order = new_order


# --------------------------------------------------------------------------- ids and plants

def assign_ids(w):
    custs = sorted(w.customers, key=lambda c: (c.created_at, c.email))
    for i, c in enumerate(custs, 1):
        c.id = i
    w.customers = custs
    orders = sorted(w.orders, key=lambda o: (o.date, o.cust.id, o.items[0][0] if o.items else 0, o.total))
    special = ("eu_legacy", "pos_v2")
    for p in range(len(orders)):
        # keep source-wide rows off round-number ids by swapping with a non-special neighbour
        if (p + 1) % 100 == 0 and orders[p].source in special:
            for q in (p + 1, p - 1):
                if 0 <= q < len(orders) and orders[q].source not in special:
                    orders[p], orders[q] = orders[q], orders[p]
                    break
    for i, o in enumerate(orders, 1):
        o.id = i
        o.date_text = {"iso": iso(o.date), "dmy": o.date.strftime("%d/%m/%Y"),
                       "mdy": o.date.strftime("%m/%d/%Y")}[o.date_style]
    w.orders = orders
    n_item = n_pay = 0
    for o in orders:
        for it in o.items:
            n_item += 1
            it.append(n_item)  # item id at index 4
        for p in o.payments:
            n_pay += 1
            p.append(n_pay)    # payment id at index 3
    for o in orders:
        for r in o.refunds:
            r["order"] = o
    refs = [(r["date"], o.id, r) for o in orders for r in o.refunds]
    refs.sort(key=lambda t: (t[0], t[1]))
    for i, (_, oid, r) in enumerate(refs, 1):
        r["id"] = i
    w.refund_rows = refs


class Planter:
    def __init__(self, seed):
        self.rng = random.Random(seed + 1)
        self.used: set[int] = set()
        self.counts: dict[str, int] = {}
        self.truth: dict[int, list] = {}  # order_id -> [expect_cents, expect_quarantine, tag]

    def pick(self, pool, k, tag):
        cand = pool[:]
        self.rng.shuffle(cand)
        chosen = []
        for o in cand:
            if len(chosen) == k:
                break
            i = o.id
            if i % 100 == 0 or i in self.used or i - 1 in self.used or i + 1 in self.used:
                continue
            self.used.add(i)
            chosen.append(o)
        assert len(chosen) == k, f"not enough eligible rows for {tag}"
        self.counts[tag] = self.counts.get(tag, 0) + k
        return chosen


def with_commas(cents: int) -> str:
    return f"{cents // 100:,}.{cents % 100:02d}"


def eu_text(cents: int, ambiguous: bool) -> str:
    if ambiguous:
        return f"{cents // 100},{cents % 100 * 10:03d}"
    whole = f"{cents // 100:,}".replace(",", ".")
    return f"{whole},{cents % 100:02d}"


def sci_text(cents: int) -> str:
    m, e = ("%.6e" % (cents / 100)).split("e")
    m = m.rstrip("0").rstrip(".")
    return f"{m}e{e}"


def plant_exp1(w, seed):
    P = Planter(seed)
    rng = P.rng
    for o in w.orders:
        c = o.total
        P.truth[o.id] = [c, 0, None]
        o.amount_text = cents_text(c)
    pool = [o for o in w.orders if o.cust.tag is None and o.source in ("web", "mobile", "marketplace")
            and o.status == "completed" and not o.cast]
    big = [o for o in pool if 100000 <= o.total < 500000]
    small = [o for o in pool if 3000 <= o.total < 100000]
    medium = [o for o in pool if o.total < 500000]
    SYM = ["$", "€", "£"]

    # L1-01 symbols / thousands commas
    for o in P.pick(big, 16, "L1-01"):
        o.amount_text = rng.choice(["", "", SYM[rng.randrange(3)]]) + with_commas(o.total)
        P.truth[o.id][2] = "L1-01"
    for o in P.pick(small, 22, "L1-01"):
        o.amount_text = SYM[rng.randrange(3)] + cents_text(o.total)
        P.truth[o.id][2] = "L1-01"
    # L1-02 scientific notation
    for o in P.pick(medium, 6, "L1-02"):
        o.amount_text = sci_text(o.total)
        P.truth[o.id][2] = "L1-02"
    # L1-03 eu_legacy decimal commas, L1-07 pos_v2 cents
    eu = [o for o in w.orders if o.source == "eu_legacy"]
    for o in eu:
        amb = o.kind == "cheap"
        o.amount_text = eu_text(o.total, amb)
        P.truth[o.id][2] = "L1-03"
    P.counts["L1-03"] = len(eu)
    pos = [o for o in w.orders if o.source == "pos_v2"]
    for o in pos:
        o.amount_text = str(o.total)
        P.truth[o.id][2] = "L1-07"
    P.counts["L1-07"] = len(pos)
    for o in eu + pos:
        P.used.add(o.id)
    # L1-04 accounting negatives
    adj = [o for o in w.orders if o.status == "adjustment"]
    for k, o in enumerate(adj):
        if k % 2 == 0:
            o.amount_text = f"({cents_text(-o.total)})"
            P.truth[o.id][2] = "L1-04"
            P.counts["L1-04"] = P.counts.get("L1-04", 0) + 1
    # L1-05 blanks and real NULLs
    kinds = ["", ""] * 3 + [" "] * 4 + ["null"] * 4 + ["N/A"] * 5 + [None] * 5
    for o, kd in zip(P.pick(pool, len(kinds), "L1-05"), kinds):
        o.amount_text = kd
        P.truth[o.id][0] = None
        P.truth[o.id][1] = 0 if kd is None else 1
        P.truth[o.id][2] = "L1-05"
    # L1-06 invisible characters
    for o in P.pick(big, 4, "L1-06"):
        o.amount_text = f"{o.total // 100 // 1000}\u00a0{o.total // 100 % 1000:03d}.{o.total % 100:02d}"
        P.truth[o.id][2] = "L1-06"
    zw = ["{}\u200b", "\u200b{}", "{}"]
    for k, o in enumerate(P.pick(small, 5, "L1-06")):
        t = cents_text(o.total)
        o.amount_text = [t + "\u200b", "\u200b" + t, t[:1] + "\u200b" + t[1:], t + "\u200b", t[:2] + "\u200b" + t[2:]][k]
        P.truth[o.id][2] = "L1-06"
    for k, o in enumerate(P.pick(small, 5, "L1-06")):
        t = cents_text(o.total)
        o.amount_text = ("\t" + t) if k % 2 == 0 else (t + "\t")
        P.truth[o.id][2] = "L1-06"
    # L1-08 sentinels
    for k, o in enumerate(P.pick(pool, 10, "L1-08")):
        o.amount_text = "-1" if k < 5 else "-999"
        P.truth[o.id][0] = None
        P.truth[o.id][1] = 1
        P.truth[o.id][2] = "L1-08"
    # L1-09 currency codes
    for k, o in enumerate(P.pick(small, 4, "L1-09")):
        t = cents_text(o.total)
        o.amount_text = [f"USD {t}", f"{t} EUR", f"CAD {t}", f"{t} GBP"][k]
        o.currency = None
        P.truth[o.id][2] = "L1-09"
    # L1-10 three-decimal values where float rounding disagrees with round-half-up
    probe = sqlite3.connect(":memory:")
    cands = []
    cp = [o for o in pool if 1000 <= o.total < 90000]
    rng.shuffle(cp)
    for o in cp:
        text = f"{(o.total * 10 - 5) // 1000}.{(o.total * 10 - 5) % 1000:03d}"
        r = probe.execute("select round(cast(? as real), 2)", (text,)).fetchone()[0]
        if round(r * 100) != o.total:
            cands.append((o, text))
        if len(cands) >= 40:
            break
    picked = P.pick([o for o, _ in cands], 9, "L1-10")
    tmap = dict((o.id, t) for o, t in cands)
    for o in picked:
        o.amount_text = tmap[o.id]
        P.truth[o.id][2] = "L1-10"
    w.planter = P
    return P


# --------------------------------------------------------------------------- writing

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_acme(w, path: Path, seed: int):
    rng = random.Random(seed + 2)
    if path.exists():
        common.make_writable(path)
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    for n in ("001_core_tables", "002_orders_and_payments", "003_activity_and_logs"):
        conn.executescript(_read(MIG_DIR / f"{n}.up.sql"))
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    conn.executemany("INSERT INTO regions VALUES (?,?,?)", w.regions)
    conn.executemany("INSERT INTO categories VALUES (?,?)", w.categories)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?)",
                     [(p[0], p[1], p[2], p[3], p[4] / 100.0) for p in w.products])
    rows = [(c.id, c.email, c.full_name, c.phone, c.region_id, c.status, c.created_at, c.updated_at,
             c.legacy_id, c.source_system) for c in w.customers]
    rng.shuffle(rows)
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    addr_rows = []
    aid = 0
    for c in w.customers:
        for a in c.addresses:
            aid += 1
            addr_rows.append((aid, c.id, a["line1"], a["city"], a["postal"], a["primary"], a["updated_at"]))
    rng.shuffle(addr_rows)
    conn.executemany("INSERT INTO customer_addresses VALUES (?,?,?,?,?,?,?)", addr_rows)
    orows = [(o.id, o.cust.id, o.date_text, o.amount_text, o.currency, o.status, o.source) for o in w.orders]
    rng.shuffle(orows)
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orows)
    irows, prows = [], []
    for o in w.orders:
        for pid, q, price, disc, iid in o.items:
            irows.append((iid, o.id, pid, q, cents_text(price), disc))  # item id was appended at index 4
        for cents, st, paid_at, payid in o.payments:
            prows.append((payid, o.id, cents / 100.0, st, paid_at))
    rng.shuffle(irows); rng.shuffle(prows)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", irows)
    conn.executemany("INSERT INTO payments VALUES (?,?,?,?,?)", prows)
    rrows = []
    for _, oid, r in w.refund_rows:
        ref_oid = oid
        if r["style"] == "ord":
            ref_oid = f"ORD-{oid}"
        elif r["style"] == "missing":
            ref_oid = len(w.orders) + 500 + (r["id"] * 37) % 9000
        cust = r.get("customer_id", r["order"].cust.id)
        rrows.append((r["id"], ref_oid, cust, cents_text(r["cents"]), ts(r["date"], rng)))
    rng.shuffle(rrows)
    conn.executemany("INSERT INTO refunds VALUES (?,?,?,?,?)", rrows)
    # sessions
    weights = [len(c.orders) + 1 for c in w.customers]
    sess = []
    chosen = rng.choices(w.customers, weights=weights, k=50000)
    for i, c in enumerate(chosen, 1):
        lo = max(START, c.created_d)
        d = lo + dt.timedelta(days=rng.randint(0, max(0, (END - lo).days)))
        login = None if rng.random() < 0.01 else ts(d, rng, 0, 23)
        sess.append((i, c.id, login, rng.choice(["web", "ios", "android"])))
    conn.executemany("INSERT INTO sessions VALUES (?,?,?,?)", sess)
    # legacy map
    maps = []
    for c in w.customers:
        if c.legacy_id:
            maps.append((len(maps) + 1, c.legacy_id, c.id))
    conn.executemany("INSERT INTO legacy_customer_map VALUES (?,?,?)", maps)
    # historical audit rows
    aud = []
    for i in range(1, 401):
        c = rng.choice(w.customers)
        aud.append((i, c.id, rng.choice(["created", "status_changed", "updated"]), ts(_rand_date(rng, D(2023, 1, 1), D(2025, 5, 31)), rng, 0, 23)))
    conn.executemany("INSERT INTO customers_audit VALUES (?,?,?,?)", aud)
    conn.executescript(_read(MIG_DIR / "004_reporting_objects.up.sql"))
    for ver, name in (("001", "core_tables"), ("002", "orders_and_payments"),
                      ("003", "activity_and_logs"), ("004", "reporting_objects")):
        conn.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (ver, name, "2025-01-15 09:00:00"))
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def write_truth(w, path: Path):
    if path.exists():
        common.make_writable(path)
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE truth_orders (order_id INTEGER PRIMARY KEY, source_system TEXT, expect_cents INTEGER,
                                   expect_quarantine INTEGER, tag TEXT);
        CREATE TABLE plants (landmine_id TEXT PRIMARY KEY, n INTEGER);
    """)
    conn.executemany("INSERT INTO truth_orders VALUES (?,?,?,?,?)",
                     [(o.id, o.source, w.planter.truth[o.id][0], w.planter.truth[o.id][1], w.planter.truth[o.id][2])
                      for o in w.orders])
    conn.executemany("INSERT INTO plants VALUES (?,?)", sorted(w.planter.counts.items()))
    for fn in getattr(w, "truth_writers", []):
        fn(conn)
    conn.commit()
    conn.close()


def build(seed: int = common.SEED, db_path: Path = ACME_DB, truth_path: Path = TRUTH_DB) -> dict:
    from . import plant2  # noqa: F401  (registers its hooks)
    try:
        from . import plant3  # noqa: F401
    except ImportError:
        pass
    w = build_world(seed)
    for fn in getattr(sys_modules_hooks, "pre_id", []):
        fn(w, seed)
    assign_ids(w)
    plant_exp1(w, seed)
    for fn in getattr(sys_modules_hooks, "post_id", []):
        fn(w, seed)
    write_acme(w, db_path, seed)
    write_truth(w, truth_path)
    return dict(customers=len(w.customers), orders=len(w.orders))


class sys_modules_hooks:  # extension points filled by plant2 / plant3 modules
    pre_id: list = []
    post_id: list = []


def main() -> None:
    info = build()
    print(f"seeded {ACME_DB} and {TRUTH_DB}: {info}")
