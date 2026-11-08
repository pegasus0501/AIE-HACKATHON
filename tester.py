import os

from uagents import Agent, Context

from agent_core import clarification_prompt, turn
from events import log_event
from messages import Clarification, TaskAssigned


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


def make_tester() -> Agent:
    agent = _agent("tester")
    orch = os.environ["ORCHESTRATOR_ADDRESS"]
    tasks: dict[str, dict] = {}

    @agent.on_message(TaskAssigned)
    async def on_task(ctx: Context, sender: str, msg: TaskAssigned):
        if sender != orch or msg.role != "tester":
            ctx.logger.warning(f"ignored TaskAssigned from {sender[:14]}... role={msg.role}")
            log_event("agent_ignored", agent="tester", type="TaskAssigned", sender=sender[:14], role=msg.role)
            return
        log_event("agent_received", agent="tester", type="TaskAssigned", task_id=msg.task_id, round=msg.round)
        mem = tasks[msg.task_id] = {"ticket": msg.ticket}
        ctx.logger.info(f"[{msg.task_id}] reading the requirement")
        await turn(ctx, "tester", orch, msg.task_id, msg.round, f"Requirement:\n{msg.contract}", msg.ticket, mem, True)

    @agent.on_message(Clarification)
    async def on_clarification(ctx: Context, sender: str, msg: Clarification):
        if sender != orch or msg.task_id not in tasks:
            ctx.logger.warning(f"ignored Clarification from {sender[:14]}...")
            log_event("agent_ignored", agent="tester", type="Clarification", sender=sender[:14])
            return
        log_event("agent_received", agent="tester", type="Clarification", task_id=msg.task_id, round=msg.round)
        mem = tasks[msg.task_id]
        await turn(ctx, "tester", orch, msg.task_id, msg.round, clarification_prompt(mem["prompt"], msg.answers),
                   mem["ticket"], mem, False)

    return agent


if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()
    os.environ["USE_MAILBOX"] = "1"
    # Python 3.14 no longer creates a default event loop; uagents 0.26.1 expects one.
    asyncio.set_event_loop(asyncio.new_event_loop())
    agent = make_tester()
    print(f"tester address: {agent.address}")
    agent.run()
