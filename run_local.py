"""Stage A: all three agents in one Bureau, stub LLM, one startup ticket."""

import asyncio
import os
import secrets

from dotenv import load_dotenv

load_dotenv()  # .env may hold real settings; the stage-A values below always win

os.environ["STUB_LLM"] = "1"
os.environ["REPORT_EVENTS"] = "0"  # skip the Agentverse telemetry lookup that can stall startup offline
os.environ["STUB_SCENARIO"] = "fail_then_pass"
os.environ.setdefault("EVENTS_FILE", "events.jsonl")
os.environ.setdefault("STARTUP_TICKET", "Add a function add(a, b) in src/calc.py that returns the sum of a and b.")
for name in ("ORCHESTRATOR", "ENGINEER", "TESTER"):
    os.environ.pop(f"{name}_PORT", None)  # Bureau serves one port
    os.environ[f"{name}_SEED"] = secrets.token_hex(16)  # throwaway seeds, never the real ones

# Python 3.14 no longer creates a default event loop; uagents 0.26.1 expects one.
asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Bureau  # noqa: E402
from uagents.crypto import Identity  # noqa: E402

for name in ("ORCHESTRATOR", "ENGINEER", "TESTER"):
    os.environ[f"{name}_ADDRESS"] = Identity.from_seed(os.environ[f"{name}_SEED"], 0).address

from engineer import make_engineer  # noqa: E402
from orchestrator import make_orchestrator  # noqa: E402
from tester import make_tester  # noqa: E402

if __name__ == "__main__":
    bureau = Bureau(port=8000)
    for make in (make_orchestrator, make_engineer, make_tester):
        bureau.add(make())
    bureau.run()
