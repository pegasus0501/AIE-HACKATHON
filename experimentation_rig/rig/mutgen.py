"""Generate mutants/<ticket>/<landmine_id>/ from reference/<ticket>/ by applying small, exact edits.

Edit kinds:
  ("sub", relpath, old, new)       exact substring, must occur exactly once
  ("def", relpath, name, source)   replace a top-level function body (found via ast)
"""
from __future__ import annotations

import ast

from . import common, workspace

UP = "migrations/005_orders_amount_numeric.up.sql"

TRIGGER_BLOCK = """CREATE TRIGGER trg_orders_touch_customer
AFTER INSERT ON orders
BEGIN
    UPDATE customers SET updated_at = datetime('now') WHERE customer_id = NEW.customer_id;
    INSERT INTO customers_audit (customer_id, action, changed_at)
    VALUES (NEW.customer_id, 'order_added', datetime('now'));
END;
"""

SPECS: dict = {
    "exp1": {
        "L1-01": [("sub", UP, "            ELSE replace(inner, ',', '')", "            ELSE inner")],
        "L1-02": [("sub", UP,
                   "            WHEN a NOT GLOB '*[^0-9.eE+-]*' AND a GLOB '[0-9]*[eE]*' AND length(a) - "
                   "length(replace(replace(a, 'e', ''), 'E', '')) = 1 THEN 'sci'\n", "")],
        "L1-03": [("sub", UP, "WHEN 'eu_legacy' THEN replace(replace(inner, '.', ''), ',', '.')",
                   "WHEN 'eu_legacy' THEN replace(inner, ',', '')")],
        "L1-04": [("sub", UP,
                   "       CASE WHEN s LIKE '(%)' THEN 1 ELSE 0 END AS paren,\n"
                   "       CASE WHEN s LIKE '(%)' THEN substr(s, 2, length(s) - 2) ELSE s END AS inner",
                   "       0 AS paren,\n       s AS inner")],
        "L1-05": [("sub", UP, "            WHEN a = '' THEN 'blank'\n", "            WHEN a = '' THEN 'plain'\n")],
        "L1-06": [("sub", UP,
                   "replace(replace(replace(replace(replace(amount, char(160), ''), char(8203), ''), "
                   "char(65279), ''), char(9), ''), ' ', '') AS s1",
                   "replace(amount, ' ', '') AS s1")],
        "L1-07": [("sub", UP, "WHEN source_system = 'pos_v2' AND instr(a, '.') = 0 THEN CAST(a AS INTEGER)",
                   "WHEN source_system = 'pos_v2' AND instr(a, '.') = 0 THEN CAST(a AS INTEGER) * 100")],
        "L1-08": [("sub", UP, "            WHEN n IN ('-1', '-999') THEN 'placeholder'\n", "")],
        "L1-09": [("sub", UP,
                   "replace(replace(replace(replace(replace(replace(replace(replace(s1, '$', ''), '€', ''), "
                   "'£', ''), '¥', ''), 'USD', ''), 'EUR', ''), 'GBP', ''), 'CAD', '') AS s",
                   "replace(replace(replace(replace(s1, '$', ''), '€', ''), '£', ''), '¥', '') AS s")],
        "L1-10": [("sub", UP,
                   "                     ELSE CAST(CASE WHEN ip = '' THEN '0' ELSE ip END AS INTEGER) * 100\n"
                   "                          + CAST(substr(fp || '00', 1, 2) AS INTEGER)\n"
                   "                          + CASE WHEN CAST(substr(fp || '000', 3, 1) AS INTEGER) >= 5 "
                   "THEN 1 ELSE 0 END\n",
                   "                     ELSE CAST(ROUND(ROUND(CAST(a AS REAL), 2) * 100) AS INTEGER)\n")],
        "L1-11": [("sub", UP, TRIGGER_BLOCK, "")],
    },
    "exp2": {
        "L2-01": [("sub", "src/reports.py",
                   '        captured = sum(a for a, st in payments_by_order.get(order_id, []) if st == "captured")',
                   '        captured = sum(a for a, st in payments_by_order.get(order_id, []) if st == "captured") '
                   "* max(1, len(payments_by_order.get(order_id, [])))")],
        "L2-02": [("sub", "src/reports.py",
                   "    text = str(raw).strip()\n    if text.upper().startswith(\"ORD-\"):\n        text = text[4:]\n"
                   "    try:\n        return int(text)\n    except ValueError:\n        return None",
                   "    try:\n        return int(raw)\n    except (ValueError, TypeError):\n        return None")],
        "L2-03": [("sub", "src/reports.py",
                   "        region_name = top_name.get(region_id, \"Unassigned\") if region_id is not None else \"Unassigned\"",
                   "        if region_id is None:\n            continue\n        region_name = top_name.get(region_id, \"Unassigned\")")],
        "L2-04": [("sub", "src/reports.py",
                   "            rank = 1 + sum(1 for other in pids if net.get(other, 0.0) > n)",
                   "            rank = 1 + sorted(pids, key=lambda q: -net.get(q, 0.0)).index(pid)")],
        "L2-05": [("sub", "src/reports.py",
                   "    if payment_dates:\n        pivot = min(payment_dates)\n        return cand_mdy if abs((cand_mdy - pivot).days) <= abs((cand_dmy - pivot).days) else cand_dmy\n    return cand_mdy",
                   "    return cand_mdy")],
        "L2-06": [("sub", "src/reports.py",
                   "    m = _SLASH.match(raw)\n    if not m:\n        return None\n"
                   "    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))\n"
                   "    cand_mdy = _safe_date(y, a, b)  # first component is the month\n"
                   "    cand_dmy = _safe_date(y, b, a)  # first component is the day\n"
                   "    if cand_mdy and not cand_dmy:\n        return cand_mdy\n"
                   "    if cand_dmy and not cand_mdy:\n        return cand_dmy\n"
                   "    if not cand_mdy and not cand_dmy:\n        return None\n"
                   "    if payment_dates:\n        pivot = min(payment_dates)\n"
                   "        return cand_mdy if abs((cand_mdy - pivot).days) <= abs((cand_dmy - pivot).days) else cand_dmy\n"
                   "    return cand_mdy",
                   "    return None")],
        "L2-07": [("sub", "src/reports.py",
                   "        if (status or \"\").strip().lower() in _CANCELLED:",
                   "        if (status or \"\") == \"cancelled\":")],
        "L2-08": [("sub", "src/reports.py",
                   "    groups: dict = {}\n    for cid, email, region_id in customers:\n        groups.setdefault(_normalize_email(email), []).append((cid, region_id))\n"
                   "    person_of, person_region = {}, {}\n    for members in groups.values():\n        members.sort(key=lambda m: m[0])\n"
                   "        pid, region = members[0]\n        for cid, _ in members:\n            person_of[cid] = pid\n        person_region[pid] = region",
                   "    person_of, person_region = {}, {}\n    for cid, email, region_id in customers:\n        person_of[cid] = cid\n        person_region[cid] = region_id")],
        "L2-09": [("sub", "src/reports.py",
                   "            pct_change = round((n - p) * 100.0 / p, 2) if p > 0 else None",
                   "            pct_change = (n - p) * 100 // p if p > 0 else None")],
        "L2-10": [("sub", "src/reports.py",
                   "        revenue = captured - refunds_by_order.get(order_id, 0.0)",
                   "        revenue = max(0.0, captured - refunds_by_order.get(order_id, 0.0))")],
        "L2-11": [("sub", "src/reports.py",
                   "    cur_start = as_of_date.fromordinal(as_of_date.toordinal() - 89)",
                   "    cur_start = as_of_date.fromordinal(as_of_date.toordinal() - 90)")],
        "L2-12": [("sub", "src/reports.py",
                   "        cur = rid\n        seen = set()\n        while parent.get(cur) is not None and cur not in seen:\n            seen.add(cur)\n            cur = parent[cur]\n        top[rid] = name[cur]",
                   "        top[rid] = name[rid]")],
    },
    "exp3": {},
}


def _apply_sub(text: str, old: str, new: str, where: str) -> str:
    n = text.count(old)
    if n != 1:
        raise ValueError(f"{where}: expected exactly one match, found {n}")
    return text.replace(old, new)


def _apply_def(text: str, name: str, source: str, where: str) -> str:
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise ValueError(f"{where}: function {name} not found exactly once")
    node = nodes[0]
    start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
    lines = text.splitlines(keepends=True)
    new_lines = lines[:start] + [source if source.endswith("\n") else source + "\n"] + lines[node.end_lineno:]
    return "".join(new_lines)


def reference_files(ticket: str) -> dict:
    tree = workspace.read_tree(common.REFERENCE_DIR / ticket)
    return {k: v for k, v in tree.items() if not k.startswith("tests/")}


def build_mutant(ticket: str, landmine: str) -> dict:
    files = dict(reference_files(ticket))
    for edit in SPECS[ticket][landmine]:
        kind, rel = edit[0], edit[1]
        where = f"{ticket}/{landmine}/{rel}"
        if kind == "sub":
            files[rel] = _apply_sub(files[rel], edit[2], edit[3], where)
        elif kind == "def":
            files[rel] = _apply_def(files[rel], edit[2], edit[3], where)
        else:
            raise ValueError(kind)
    return files


def mutant_ids(ticket: str) -> list:
    return list(SPECS[ticket].keys())


def generate(tickets=None) -> dict:
    """Write mutants/<ticket>/<id>/ trees. Returns {ticket: [ids]}."""
    done = {}
    for ticket in tickets or common.TICKETS:
        ids = mutant_ids(ticket)
        if not ids:
            continue
        base = common.MUTANTS_DIR / ticket
        common.rmtree(base)
        for lid in ids:
            for rel, text in build_mutant(ticket, lid).items():
                target = base / lid / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
        done[ticket] = ids
    return done


def load_mutant(ticket: str, landmine: str) -> dict:
    return workspace.read_tree(common.MUTANTS_DIR / ticket / landmine)
