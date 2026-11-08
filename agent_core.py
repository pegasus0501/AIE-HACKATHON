"""One model turn shared by the Engineer and Tester: inspect the data, maybe push back, then submit."""

import asyncio
import time

from events import log_event
from llm import build_system, call_model
from messages import PushBack, Submission


def clarification_prompt(base_prompt: str, answers: list[dict]) -> str:
    qa = "\n".join(f"- Q: {a['question']}\n  A: {a['answer']}" for a in answers)
    return f"{base_prompt}\n\nCLARIFICATIONS from the requirements owner (final, do not ask again):\n{qa}"


async def turn(ctx, role, orch, task_id, rnd, prompt, ticket, mem, allow_pushback):
    """Returns the model output when files were submitted, or None when the agent pushed back instead."""

    def emit(kind, **fields):
        log_event(kind, agent=role, task_id=task_id, round=rnd, **fields)

    query_fn = None
    full = prompt
    if ticket:
        import rig_bridge

        query_fn = lambda sql: rig_bridge.sql(ticket, sql)  # noqa: E731
        full = f"{prompt}\n\n{rig_bridge.repo_context(ticket, role)}"
    system = build_system(role, rig=bool(ticket), allow_pushback=allow_pushback)
    t0 = time.monotonic()
    try:
        out = await asyncio.to_thread(call_model, role, system, full, rnd, query_fn, emit, allow_pushback)
    except Exception as e:
        emit("model_error", error=f"{type(e).__name__}: {str(e)[:300]}")
        raise
    emit("model_call", seconds=round(time.monotonic() - t0, 1), files=list(out["files"]), queries=out.get("queries", 0))

    blocking = [p for p in out["pushback"] if p["blocking"]]
    if allow_pushback and blocking and not out["files"]:
        mem["prompt"] = prompt
        items = [{"point": p["point"], "question": p["question"]} for p in blocking]
        await ctx.send(orch, PushBack(task_id=task_id, role=role, round=rnd, items=items))
        emit("agent_sent", type="PushBack")
        return None
    doubts = [{"point": p["point"], "question": p["question"]} for p in out["pushback"]]
    await ctx.send(
        orch,
        Submission(task_id=task_id, role=role, round=rnd, files=out["files"], notes=out["notes"],
                   assumptions=out["assumptions"], pushback=doubts),
    )
    emit("agent_sent", type="Submission")
    return out
