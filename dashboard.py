"""Local dashboard: python dashboard.py  ->  http://127.0.0.1:8050

Reads events.jsonl (written by all three agents) and serves a live task-lineage view.
Binds to localhost only.
"""

import difflib
import json
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

import rig_bridge

load_dotenv()
HERE = Path(__file__).parent
MAX_EVENTS = 20000
MAX_DIFF_LINES = 400
TASK_ID = re.compile(r"^[0-9a-f]{8}$")
ROLE_ORDER = {"engineer": 0, "tester": 1}
QUEUE_DIR = Path(os.getenv("QUEUE_DIR", "queue"))
MAX_BODY = 1024


def read_events() -> list[dict]:
    path = Path(os.getenv("EVENTS_FILE", "events.jsonl"))
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f.readlines()[-MAX_EVENTS:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a half-written line from another process
    return events


def agent_map() -> dict[str, str]:
    out = {}
    for name in ("orchestrator", "engineer", "tester"):
        addr = os.getenv(f"{name.upper()}_ADDRESS")
        if addr:
            out[addr] = name
    return out


def diff_entry(path: str, old: str | None, new: str) -> dict:
    """Diff one file against the same role's previous version of it."""
    new_lines = new.splitlines()
    if old is None:
        status, lines = "added", [("add", ln) for ln in new_lines]
    elif old == new:
        status, lines = "unchanged", []
    else:
        status, lines = "modified", []
        for ln in difflib.unified_diff(old.splitlines(), new_lines, lineterm="", n=3):
            if ln.startswith(("---", "+++")):
                continue
            if ln.startswith("@@"):
                lines.append(("hdr", ln))
            elif ln.startswith("+"):
                lines.append(("add", ln[1:]))
            elif ln.startswith("-"):
                lines.append(("del", ln[1:]))
            else:
                lines.append(("ctx", ln[1:]))
    return {
        "path": path,
        "status": status,
        "adds": sum(1 for t, _ in lines if t == "add"),
        "dels": sum(1 for t, _ in lines if t == "del"),
        "truncated": len(lines) > MAX_DIFF_LINES,
        "lines": lines[:MAX_DIFF_LINES],
    }


def build_task(task_id: str) -> dict | None:
    """Contract plus every submission with per-file diffs. None if nothing was saved."""
    if not TASK_ID.match(task_id):
        return None
    base = Path(os.getenv("WORKSPACE_DIR", "workspace")) / task_id
    sub_dir = base / "submissions"
    if not sub_dir.is_dir():
        return None
    contract = ""
    if (base / "contract.txt").exists():
        contract = (base / "contract.txt").read_text(encoding="utf-8")
    subs = []
    for p in sub_dir.glob("r*_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d["role"] in ROLE_ORDER and isinstance(d["files"], dict):
                subs.append(d)
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    subs.sort(key=lambda d: (d["round"], ROLE_ORDER[d["role"]]))
    prev: dict[str, dict[str, str]] = {"engineer": {}, "tester": {}}
    out = []
    for d in subs:
        files = []
        for path, content in sorted(d["files"].items()):
            files.append(diff_entry(path, prev[d["role"]].get(path), str(content)))
            prev[d["role"]][path] = str(content)
        out.append({
            "round": d["round"], "role": d["role"], "notes": d.get("notes", ""),
            "assumptions": d.get("assumptions", []), "pushback": d.get("pushback", []),
            "rejected": d.get("rejected", []), "files": files,
        })
    return {"contract": contract, "submissions": out}


def tickets_payload(events: list[dict]) -> list[dict]:
    """The tickets (fixed, no status) and every run made on each of them, newest first."""
    outcome: dict[str, str] = {}
    for e in events:
        if e.get("kind") == "decision":
            outcome[e["task_id"]] = {"pass": "pass", "fail_final": "fail", "timeout": "fail"}.get(e.get("outcome"), "running")
    runs: dict[str, list] = {}
    for e in events:
        if e.get("kind") == "task_created" and e.get("ticket_id"):
            runs.setdefault(e["ticket_id"], []).append(
                {"task_id": e["task_id"], "ts": e["ts"], "outcome": outcome.get(e["task_id"], "running")})
    return [
        {"id": t["id"], "title": t["title"], "text": rig_bridge.ticket_text(t["id"]), "runs": list(reversed(runs.get(t["id"], [])))}
        for t in rig_bridge.issues()
    ]


def queue_run(ticket_id: str) -> str:
    """Ask the Orchestrator to start a run. It claims files from QUEUE_DIR; no chat session is involved."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    tmp = QUEUE_DIR / f"{name}.part"
    tmp.write_text(json.dumps({"ticket_id": ticket_id}), encoding="utf-8")
    tmp.rename(QUEUE_DIR / f"{name}.json")  # appears atomically; the Orchestrator only reads *.json
    return name


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/events"):
            body = json.dumps({"events": read_events(), "agents": agent_map()}).encode()
            self._send(200, body, "application/json")
        elif self.path.startswith("/api/tickets"):
            self._send(200, json.dumps(tickets_payload(read_events())).encode(), "application/json")
        elif self.path.startswith("/api/task/"):
            data = build_task(self.path.split("?")[0][len("/api/task/"):])
            if data is None:
                self._send(404, b"{}", "application/json")
            else:
                self._send(200, json.dumps(data).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        port = int(os.getenv("DASHBOARD_PORT", "8050"))
        own = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        if self.path != "/api/run":
            return self._send(404, b"not found", "text/plain")
        if self.headers.get("Host") not in own or (origin and origin.split("//", 1)[-1] not in own):
            return self._send(403, b'{"error":"forbidden"}', "application/json")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(415, b'{"error":"send application/json"}', "application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError
            ticket_id = str(json.loads(self.rfile.read(length))["ticket_id"])
        except (ValueError, KeyError, TypeError):
            return self._send(400, b'{"error":"expected {\\"ticket_id\\": ...}"}', "application/json")
        if not rig_bridge.is_issue(ticket_id):
            return self._send(404, b'{"error":"unknown ticket"}', "application/json")
        self._send(202, json.dumps({"queued": queue_run(ticket_id), "ticket_id": ticket_id}).encode(), "application/json")

    def log_message(self, *args):  # keep the console quiet
        pass


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8050"))
    print(f"Dashboard: http://127.0.0.1:{port}  (reading {os.getenv('EVENTS_FILE', 'events.jsonl')})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
