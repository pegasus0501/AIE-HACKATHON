import asyncio
import json
import os
import time

from uagents import Agent, Context

from events import log_event
from llm import SYSTEMS, call_model
from messages import Feedback, Submission, TaskAssigned


def make_engineer() -> Agent:
    kwargs = {}
    if os.getenv("ENGINEER_PORT"):
        kwargs["port"] = int(os.environ["ENGINEER_PORT"])
    agent = Agent(
        name="engineer",
        seed=os.getenv("ENGINEER_SEED"),
        mailbox=os.getenv("USE_MAILBOX") == "1",
        report_events=os.getenv("REPORT_EVENTS", "1") == "1",
        **kwargs,
    )
    orch = os.environ["ORCHESTRATOR_ADDRESS"]
    tasks: dict[str, dict] = {}  # task_id -> {"contract", "files"}  (engineer's own memory)

    async def work(ctx: Context, task_id: str, rnd: int, user: str):
        t0 = time.monotonic()
        try:
            out = await asyncio.to_thread(call_model, "engineer", SYSTEMS["engineer"], user, rnd)
        except Exception as e:
            log_event("model_error", agent="engineer", task_id=task_id, round=rnd, error=f"{type(e).__name__}: {str(e)[:300]}")
            raise
        log_event(
            "model_call", agent="engineer", task_id=task_id, round=rnd,
            seconds=round(time.monotonic() - t0, 1), files=list(out["files"]),
        )
        tasks[task_id]["files"].update(out["files"])
        await ctx.send(
            orch,
            Submission(task_id=task_id, role="engineer", round=rnd, files=out["files"], notes=out["notes"], assumptions=out["assumptions"]),
        )
        log_event("agent_sent", agent="engineer", type="Submission", task_id=task_id, round=rnd)

    @agent.on_message(TaskAssigned)
    async def on_task(ctx: Context, sender: str, msg: TaskAssigned):
        if sender != orch or msg.role != "engineer":
            ctx.logger.warning(f"ignored TaskAssigned from {sender[:14]}... role={msg.role}")
            log_event("agent_ignored", agent="engineer", type="TaskAssigned", sender=sender[:14], role=msg.role)
            return
        log_event("agent_received", agent="engineer", type="TaskAssigned", task_id=msg.task_id, round=msg.round)
        tasks[msg.task_id] = {"contract": msg.contract, "files": {}}
        ctx.logger.info(f"[{msg.task_id}] round {msg.round}: writing implementation")
        await work(ctx, msg.task_id, msg.round, f"Contract:\n{msg.contract}")

    @agent.on_message(Feedback)
    async def on_feedback(ctx: Context, sender: str, msg: Feedback):
        if sender != orch or msg.task_id not in tasks:
            ctx.logger.warning(f"ignored Feedback from {sender[:14]}...")
            log_event("agent_ignored", agent="engineer", type="Feedback", sender=sender[:14])
            return
        log_event("agent_received", agent="engineer", type="Feedback", task_id=msg.task_id, round=msg.round)
        t = tasks[msg.task_id]
        ctx.logger.info(f"[{msg.task_id}] round {msg.round}: fixing after feedback")
        user = (
            f"Contract:\n{t['contract']}\n\nYour current files:\n{json.dumps(t['files'], indent=2)}\n\n"
            f"Test failures (names and assertion lines only):\n{msg.report}\n\nFix the implementation."
        )
        await work(ctx, msg.task_id, msg.round, user)

    return agent


if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()
    os.environ["USE_MAILBOX"] = "1"
    # Python 3.14 no longer creates a default event loop; uagents 0.26.1 expects one.
    asyncio.set_event_loop(asyncio.new_event_loop())
    agent = make_engineer()
    print(f"engineer address: {agent.address}")
    agent.run()
