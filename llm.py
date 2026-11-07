"""Meta model layer. Every call builds a fresh message list: no shared context between agents."""

import json
import os
import re

MAX_QUERIES = 6
NOT_SPECIFIED = "Not specified in the approved contract. Decide, and record it as an assumption."

BASE = {
    "engineer": (
        "You are the Engineer. Implement the contract with the minimal correct change and make it work. "
        "You may only write files under migrations/, queries/ or src/. "
        "Use only modules, functions and tables that exist or that you create; never invent APIs."
    ),
    "tester": (
        "You are the Tester. Be skeptical. From the requirement and the real data, write pytest tests that "
        "try to break the implementation. You may only write files under tests/. "
        "Test the data as it really is, not as you wish it were."
    ),
}
FINAL = (
    ' Final reply, JSON only: {"files": {"path": "full file content"}, "notes": "%s", '
    '"assumptions": ["each assumption you made that the requirement does not state"], '
    '"pushback": [{"point": "...", "question": "...", "blocking": false}]}'
)
NOTES = {"engineer": "why you made this change, 1-2 sentences", "tester": "what the tests cover, 1-2 sentences"}
PUSHBACK = (
    ' If the requirement is vague or has several reasonable readings, push back BEFORE guessing. Reply JSON only: '
    '{"pushback": [{"point": "what is unclear", "question": "a precise, answerable question", "blocking": true}], '
    '"files": {}}. Ask only about things that change the result. After you receive answers you must deliver files.'
)
QUERY = (
    ' You can inspect the real data with read-only SQL, one SELECT at a time: reply JSON only '
    '{"query": "SELECT ..."} and you will get the result back. Look before you decide. At most %d queries.'
)


def build_system(role: str, rig: bool = False, allow_pushback: bool = False) -> str:
    s = BASE[role] + (PUSHBACK if allow_pushback else "") + (QUERY % MAX_QUERIES if rig else "")
    return s + FINAL % NOTES[role]


# kept for check_models.py
SYSTEMS = {r: build_system(r) for r in BASE}


class ModelError(RuntimeError):
    pass


def _norm_pushback(raw) -> list[dict]:
    out = []
    for p in raw if isinstance(raw, list) else []:
        if isinstance(p, dict) and (p.get("question") or p.get("point")):
            out.append({
                "point": str(p.get("point", "")), "question": str(p.get("question", p.get("point", ""))),
                "blocking": bool(p.get("blocking", False)),
            })
    return out


def _parse(text: str) -> dict:
    t = re.sub(r"\s*```$", "", re.sub(r"^```[a-zA-Z]*\s*", "", text.strip())).strip()
    data = json.loads(t)
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    base = {"files": {}, "notes": str(data.get("notes", "")), "query": None, "pushback": _norm_pushback(data.get("pushback"))}
    raw_a = data.get("assumptions", [])
    base["assumptions"] = [str(a) for a in raw_a] if isinstance(raw_a, list) else []
    q, files = data.get("query"), data.get("files")
    if isinstance(q, str) and q.strip() and not files:
        base["query"] = q.strip()
        return base
    files = files or {}
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        raise ValueError('"files" must be {path: content}')
    base["files"] = files
    if not files and not any(p["blocking"] for p in base["pushback"]):
        raise ValueError('reply needs "files", a "query", or a blocking "pushback"')
    return base


# ---- stub (STUB_LLM=1): fixed ticket "add(a, b) in src/calc.py", no network ----

_TESTS = (
    "from src.calc import add\n\n\n"
    "def test_add_positive():\n    assert add(2, 3) == 5\n\n\n"
    "def test_add_negative():\n    assert add(-1, 1) == 0\n"
)


def _stub(role: str, round_no: int, user: str, allow_pushback: bool) -> dict:
    scenario = os.getenv("STUB_SCENARIO", "pass")
    if role == "tester":
        pb = [{"point": "Input types are not stated", "question": "Should add() accept strings?", "blocking": False}]
        return {
            "files": {"tests/test_calc.py": _TESTS}, "query": None,
            "notes": "stub tests: positive and negative sums",
            "assumptions": ["The contract only asks for the sum of two numbers (stub)"],
            "pushback": pb if scenario == "pushback" else [],
        }
    if scenario == "pushback" and allow_pushback and "CLARIFICATIONS" not in user:
        return {"files": {}, "query": None, "notes": "", "assumptions": [], "pushback": [
            {"point": "Result type", "question": "Should add() return an int or a float for int inputs?", "blocking": True},
            {"point": "Bad input", "question": "What should add() do if an argument is not a number?", "blocking": True},
        ]}
    buggy = scenario in ("fail_then_pass", "pushback") and round_no == 1
    return {
        "files": {"src/calc.py": f"def add(a, b):\n    return {'a - b' if buggy else 'a + b'}\n"}, "query": None,
        "notes": "stub engineer: subtracts instead of adds (bug)" if buggy else "stub engineer: returns a + b",
        "assumptions": ["Inputs are plain numbers (stub)"], "pushback": [],
    }


# ---- real calls ----

def _client():
    from openai import OpenAI

    if not os.getenv("MODEL_API_KEY"):
        raise ModelError("MODEL_API_KEY must be set")
    return OpenAI(
        base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
        api_key=os.environ["MODEL_API_KEY"], timeout=120, max_retries=2,
    )


def _effort() -> str:
    effort = os.getenv("REASONING_EFFORT", "low")
    if effort not in ("low", "medium"):
        raise ModelError('REASONING_EFFORT must be "low" or "medium"')
    return effort


def _model(role_env: str) -> str:
    model = os.getenv(f"{role_env}_MODEL")
    if not model:
        raise ModelError(f"{role_env}_MODEL must be set")
    return model


def call_model(role: str, system: str, user: str, round_no: int = 1, query_fn=None, emit=None,
               allow_pushback: bool = True) -> dict:
    """Return {"files","notes","assumptions","pushback","query"}.

    The model may ask for read-only SQL (query_fn runs it); every call starts from a fresh message list.
    """
    if os.getenv("STUB_LLM") == "1":
        return _stub(role, round_no, user, allow_pushback)
    client, model, effort = _client(), _model(role.upper()), _effort()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    queries, last = 0, None
    for _ in range(MAX_QUERIES + 4):
        resp = client.chat.completions.create(model=model, messages=messages, reasoning_effort=effort)
        text = resp.choices[0].message.content or ""
        try:
            out = _parse(text)
            if not allow_pushback and not out["files"] and not out["query"]:
                raise ValueError("deliver files now; further questions are not allowed")
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"Invalid ({e}). Reply with the JSON object only."}]
            continue
        if out["query"]:
            if query_fn is None or queries >= MAX_QUERIES:
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": "No more queries are available. Deliver your final reply now."}]
                continue
            queries += 1
            result = query_fn(out["query"])
            if emit:
                emit("agent_query", sql=out["query"][:600], result=result[:600])
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"RESULT:\n{result}"}]
            continue
        out["queries"] = queries
        return out
    raise ModelError(f"{role}: no valid reply after retries: {last}")


def answer_questions(contract: str, questions: list[str]) -> list[str]:
    """The Orchestrator answers an agent's questions strictly from the approved contract."""
    if os.getenv("STUB_LLM") == "1":
        return ["Per the approved contract: use your best judgement and state it as an assumption (stub)." for _ in questions]
    system = (
        "You own the requirements. Answer each question using ONLY the approved contract below; quote the decision "
        f'number when you can. If the contract does not cover it, answer exactly: "{NOT_SPECIFIED}" '
        'Reply JSON only: {"answers": ["...", ...]} in the same order as the questions.\n\nCONTRACT:\n' + contract
    )
    user = "QUESTIONS:\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    model = os.getenv("CLARIFIER_MODEL") or _model("ENGINEER")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for _ in range(3):
        text = _client().chat.completions.create(model=model, messages=messages, reasoning_effort=_effort()).choices[0].message.content or ""
        try:
            t = re.sub(r"\s*```$", "", re.sub(r"^```[a-zA-Z]*\s*", "", text.strip())).strip()
            ans = [str(a) for a in json.loads(t)["answers"]]
            if len(ans) == len(questions):
                return ans
        except (ValueError, KeyError, TypeError):
            pass
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Reply with the JSON object only, one answer per question."}]
    return [NOT_SPECIFIED for _ in questions]
