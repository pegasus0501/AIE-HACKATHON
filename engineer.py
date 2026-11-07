import json
import os

from uagents import Agent, Context

from agent_core import clarification_prompt, turn
from events import log_event
from messages import Clarification, Feedback, TaskAssigned


def _agent(name: str) -> Agent:
    kwargs = {}
    if os.getenv(f"{name.upper()}_PORT"):
        kwargs["port"] = int(os.environ[f"{name.upper()}_PORT"])
    return Agent(
        name=name,
        seed=os.getenv(f"{name.upper()}_SEED"),
        mailbox=os.getenv("USE_MAILBOX") == "1",
        report_events=os.getenv("REPORT_EVENTS", "1") == "1",
        **kwargs,
    )


def make_engineer() -> Agent:
    agent = _agent("engineer")
    orch = os.environ["ORCHESTRATOR_ADDRESS"]
    tasks: dict[str, dict] = {}  # task_id -> the engineer's own memory (contract, ticket, files, prompt)

    def ok(ctx, sender, kind, task_id=None):
        if sender != orch or (task_id is not None and task_id not in tasks):
            ctx.logger.warning(f"ignored {kind} from {sender[:14]}...")
            log_event("agent_ignored", agent="engineer", type=kind, sender=sender[:14])
            return False
        return True

    @agent.on_message(TaskAssigned)
    async def on_task(ctx: Context, sender: str, msg: TaskAssigned):
        if sender != orch or msg.role != "engineer":
            ctx.logger.warning(f"ignored TaskAssigned from {sender[:14]}... role={msg.role}")
            log_event("agent_ignored", agent="engineer", type="TaskAssigned", sender=sender[:14], role=msg.role)
            return
        log_event("agent_received", agent="engineer", type="TaskAssigned", task_id=msg.task_id, round=msg.round)
        mem = tasks[msg.task_id] = {"contract": msg.contract, "ticket": msg.ticket, "files": {}}
        ctx.logger.info(f"[{msg.task_id}] round {msg.round}: reading the requirement")
        out = await turn(ctx, "engineer", orch, msg.task_id, msg.round, f"Requirement:\n{msg.contract}", msg.ticket, mem, True)
        if out:
            mem["files"].update(out["files"])

    @agent.on_message(Clarification)
    async def on_clarification(ctx: Context, sender: str, msg: Clarification):
        if not ok(ctx, sender, "Clarification", msg.task_id):
            return
        log_event("agent_received", agent="engineer", type="Clarification", task_id=msg.task_id, round=msg.round)
        mem = tasks[msg.task_id]
        prompt = clarification_prompt(mem["prompt"], msg.answers)
        out = await turn(ctx, "engineer", orch, msg.task_id, msg.round, prompt, mem["ticket"], mem, False)
        if out:
            mem["files"].update(out["files"])

    @agent.on_message(Feedback)
    async def on_feedback(ctx: Context, sender: str, msg: Feedback):
        if not ok(ctx, sender, "Feedback", msg.task_id):
            return
        log_event("agent_received", agent="engineer", type="Feedback", task_id=msg.task_id, round=msg.round)
        mem = tasks[msg.task_id]
        ctx.logger.info(f"[{msg.task_id}] round {msg.round}: fixing after feedback")
        prompt = (
            f"Requirement:\n{mem['contract']}\n\nYour current files:\n{json.dumps(mem['files'], indent=2)}\n\n"
            f"Test failures (names and assertion lines only):\n{msg.report}\n\nFix the implementation."
        )
        out = await turn(ctx, "engineer", orch, msg.task_id, msg.round, prompt, mem["ticket"], mem, False)
        if out:
            mem["files"].update(out["files"])

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
