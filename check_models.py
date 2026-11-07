"""Stage B: call the engineer and tester models once each and print the replies."""

import json
import os

from dotenv import load_dotenv

load_dotenv()
os.environ["STUB_LLM"] = "0"  # always the real path here

from llm import SYSTEMS, ModelError, call_model  # noqa: E402

CONTRACT = "Contract:\nAdd a function add(a, b) in src/calc.py that returns the sum of a and b."

if __name__ == "__main__":
    print(f"base_url={os.getenv('META_BASE_URL', 'https://api.meta.ai/v1')} effort={os.getenv('REASONING_EFFORT', 'low')}")
    ok = True
    for role in ("engineer", "tester"):
        model = os.getenv(f"{role.upper()}_MODEL")
        print(f"\n=== {role} (model={model}) ===")
        try:
            out = call_model(role, SYSTEMS[role], CONTRACT)
            print(json.dumps(out, indent=2))
        except Exception as e:  # report, don't hide
            ok = False
            print(f"FAILED: {type(e).__name__}: {str(e)[:500]}")
    raise SystemExit(0 if ok else 1)
