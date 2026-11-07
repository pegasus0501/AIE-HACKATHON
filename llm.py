"""Meta model layer. Every call builds a fresh message list: no shared context."""

import json
import os
import re

SYSTEMS = {
    "engineer": (
        "You are the Engineer. Implement the contract with the minimal correct change "
        "and make it work. You may only write files under migrations/, queries/ or src/. "
        "Use only modules, functions and tables that exist or that you create; never invent APIs. "
        'Reply with JSON only: {"files": {"path": "full file content"}, '
        '"notes": "why you made this change, 1-2 sentences", '
        '"assumptions": ["each assumption you made that the contract does not state"]}'
    ),
    "tester": (
        "You are the Tester. Be skeptical. From the contract ONLY, write pytest tests "
        "that try to break the implementation. You may only write files under tests/. "
        'Reply with JSON only: {"files": {"path": "full file content"}, '
        '"notes": "what the tests cover, 1-2 sentences", '
        '"assumptions": ["each assumption you made that the contract does not state"]}'
    ),
}


class ModelError(RuntimeError):
    pass


def _parse(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    data = json.loads(t)
    files = data.get("files")
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in files.items()
    ):
        raise ValueError('JSON must contain "files": {path: content}')
    raw = data.get("assumptions", [])
    assumptions = [str(a) for a in raw] if isinstance(raw, list) else []
    return {"files": files, "notes": str(data.get("notes", "")), "assumptions": assumptions}


# ---- stub (STUB_LLM=1): fixed ticket "add(a, b) in src/calc.py", no network ----

_TESTS = (
    "from src.calc import add\n\n\n"
    "def test_add_positive():\n    assert add(2, 3) == 5\n\n\n"
    "def test_add_negative():\n    assert add(-1, 1) == 0\n"
)


def _stub(role: str, round_no: int) -> dict:
    if role == "tester":
        return {
            "files": {"tests/test_calc.py": _TESTS},
            "notes": "stub tests: positive and negative sums",
            "assumptions": ["The contract only asks for the sum of two numbers (stub)"],
        }
    buggy = os.getenv("STUB_SCENARIO", "pass") == "fail_then_pass" and round_no == 1
    body = "a - b" if buggy else "a + b"
    return {
        "files": {"src/calc.py": f"def add(a, b):\n    return {body}\n"},
        "notes": "stub engineer: subtracts instead of adds (bug)" if buggy else "stub engineer: returns a + b",
        "assumptions": ["Inputs are plain numbers (stub)"],
    }


# ---- real calls ----

def call_model(role: str, system: str, user: str, round_no: int = 1) -> dict:
    """Return {"files", "notes", "assumptions"}. round_no only matters for the stub."""
    if os.getenv("STUB_LLM") == "1":
        return _stub(role, round_no)

    from openai import OpenAI

    model = os.getenv(f"{role.upper()}_MODEL")
    if not model or not os.getenv("MODEL_API_KEY"):
        raise ModelError(f"{role.upper()}_MODEL and MODEL_API_KEY must be set")
    effort = os.getenv("REASONING_EFFORT", "low")
    if effort not in ("low", "medium"):
        raise ModelError('REASONING_EFFORT must be "low" or "medium"')
    client = OpenAI(
        base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
        api_key=os.environ["MODEL_API_KEY"],
        timeout=120,
        max_retries=2,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = None
    for _ in range(2):  # one retry on bad JSON
        resp = client.chat.completions.create(
            model=model, messages=messages, reasoning_effort=effort
        )
        text = resp.choices[0].message.content or ""
        try:
            return _parse(text)
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid ({e}). Reply with the JSON object only."},
            ]
    raise ModelError(f"{role}: model returned invalid JSON twice: {last}")
