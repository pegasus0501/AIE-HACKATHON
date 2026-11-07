"""Fill empty *_SEED values in .env with random seeds and write the matching *_ADDRESS.

Seeds are never printed. Existing non-empty seeds are kept.
"""

import re
import secrets
from pathlib import Path

from dotenv import dotenv_values
from uagents.crypto import Identity

ENV = Path(".env")
NAMES = ("ORCHESTRATOR", "ENGINEER", "TESTER")


def set_line(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}\s*=.*$", text, flags=re.M):
        return re.sub(rf"^{key}\s*=.*$", line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


if __name__ == "__main__":
    if not ENV.exists():
        raise SystemExit("No .env found. Copy .env.example to .env first.")
    vals = dotenv_values(ENV)
    text = ENV.read_text(encoding="utf-8")
    for n in NAMES:
        seed = (vals.get(f"{n}_SEED") or "").strip()
        if not seed:
            seed = secrets.token_hex(16)
            text = set_line(text, f"{n}_SEED", seed)
            print(f"{n}_SEED: generated")
        else:
            print(f"{n}_SEED: kept existing")
        addr = Identity.from_seed(seed, 0).address
        text = set_line(text, f"{n}_ADDRESS", addr)
        print(f"{n}_ADDRESS={addr}")
    ENV.write_text(text, encoding="utf-8")
