import asyncio
import json
import os

from uagents import Agent, Context

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
        out = await asyncio.to_thread(call_model, "engineer", SYSTEMS["engineer"], user, rnd)
        tasks[task_id]["files"].update(out["files"])
        await ctx.send(
            orch,
            Submission(task_id=task_id, role="engineer", round=rnd, files=out["files"], notes=out["notes"]),
        )

    @agent.on_message(TaskAssigned)
    async def on_task(ctx: Context, sender: str, msg: TaskAssigned):
        if sender != orch or msg.role != "engineer":
            ctx.logger.warning(f"ignored TaskAssigned from {sender[:14]}... role={msg.role}")
            return
        tasks[msg.task_id] = {"contract": msg.contract, "files": {}}
        ctx.logger.info(f"[{msg.task_id}] round {msg.round}: writing implementation")
        await work(ctx, msg.task_id, msg.round, f"Contract:\n{msg.contract}")

    @agent.on_message(Feedback)
    async def on_feedback(ctx: Context, sender: str, msg: Feedback):
        if sender != orch or msg.task_id not in tasks:
            ctx.logger.warning(f"ignored Feedback from {sender[:14]}...")
            return
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
