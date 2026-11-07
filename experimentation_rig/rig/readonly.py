"""The only way agents inspect data: single SELECT statements against a frozen snapshot."""
from __future__ import annotations

import sqlite3
import time

from . import common
from .snapshot import path_for


class QueryRejected(ValueError):
    pass


def _strip_and_check(sql: str) -> str:
    """Return the statement without comments or a trailing semicolon, or raise QueryRejected."""
    out = []
    i, n = 0, len(sql)
    quote = None
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:  # doubled quote escape
                    out.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
        elif ch == "-" and sql[i:i + 2] == "--":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        elif ch == "/" and sql[i:i + 2] == "/*":
            end = sql.find("*/", i + 2)
            if end < 0:
                raise QueryRejected("unterminated comment")
            i = end + 2
            out.append(" ")
            continue
        else:
            out.append(ch)
        i += 1
    if quote:
        raise QueryRejected("unterminated string")
    text = "".join(out).strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    # a remaining semicolon outside quotes means more than one statement
    q = None
    for ch in text:
        if q:
            if ch == q:
                q = None
        elif ch in ("'", '"', "`"):
            q = ch
        elif ch == ";":
            raise QueryRejected("only a single statement is allowed")
    head = text.lstrip("( \t\r\n").lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise QueryRejected("only SELECT statements are allowed")
    return text


_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED.add(sqlite3.SQLITE_RECURSIVE)


def _authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def query(ticket: str, sql: str, max_rows: int | None = None, timeout: float | None = None) -> dict:
    """Run one SELECT against the ticket's snapshot. Returns columns, rows and a truncation flag."""
    common.check_ticket(ticket)
    max_rows = common.QUERY_MAX_ROWS if max_rows is None else int(max_rows)
    timeout = common.QUERY_TIMEOUT if timeout is None else float(timeout)
    text = _strip_and_check(sql)
    conn = common.connect_ro(path_for(ticket))
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_authorizer)
        deadline = time.monotonic() + timeout
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        try:
            cur = conn.execute(text)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise TimeoutError(f"query exceeded {timeout} seconds") from exc
            raise QueryRejected(str(exc)) from exc
        except sqlite3.DatabaseError as exc:
            raise QueryRejected(str(exc)) from exc
        truncated = len(rows) > max_rows
        return {"columns": columns, "rows": [list(r) for r in rows[:max_rows]], "truncated": truncated}
    finally:
        conn.close()
