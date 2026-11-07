import asyncio
import os

from uagents import Agent, Context

from llm import SYSTEMS, call_model
from messages import Submission, TaskAssigned


def make_tester() -> Agent:
    kwargs = {}
    if os.getenv("TESTER_PORT"):
        kwargs["port"] = int(os.environ["TESTER_PORT"])
    agent = Agent(
        name="tester",
        seed=os.getenv("TESTER_SEED"),
        mailbox=os.getenv("USE_MAILBOX") == "1",
        report_events=os.getenv("REPORT_EVENTS", "1") == "1",
        **kwargs,
    )
    orch = os.environ["ORCHESTRATOR_ADDRESS"]

    @agent.on_message(TaskAssigned)
    async def on_task(ctx: Context, sender: str, msg: TaskAssigned):
        if sender != orch or msg.role != "tester":
            ctx.logger.warning(f"ignored TaskAssigned from {sender[:14]}... role={msg.role}")
            return
        ctx.logger.info(f"[{msg.task_id}] writing tests from the contract")
        out = await asyncio.to_thread(
            call_model, "tester", SYSTEMS["tester"], f"Contract:\n{msg.contract}", msg.round
        )
        await ctx.send(
            orch,
            Submission(task_id=msg.task_id, role="tester", round=msg.round, files=out["files"], notes=out["notes"]),
        )

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
