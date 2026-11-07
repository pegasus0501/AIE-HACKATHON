import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

from events import log_event
from messages import Feedback, Submission, TaskAssigned

ALLOWED = {"engineer": ("migrations/", "queries/", "src/"), "tester": ("tests/",)}
SECRET_HINTS = ("KEY", "SEED", "TOKEN", "SECRET", "PASSWORD")

# Seam: a model-drafted contract replaces this later.
CONTRACT_TEMPLATE = """\
TICKET:
{ticket}

CONVENTIONS:
- Python 3 project. Implementation modules live under src/ and are imported as `src.<module>`.
- Tests are pytest files under tests/ and run from the project root.
- Implement exactly what the ticket states; nothing more.
"""


def check_path(role: str, path: str) -> str | None:
    """Return an error string if `path` is not allowed for `role`, else None."""
    if not path or "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "absolute or malformed path"
    if any(p in ("", ".", "..") for p in path.split("/")):
        return "path traversal"
    if not path.startswith(ALLOWED[role]):
        return f"outside allowed folders {ALLOWED[role]}"
    return None


def run_pytest(round_dir: Path, timeout: int) -> tuple[int, str]:
    """Run pytest in a subprocess. Returns (exit_code, report). exit_code 0 == pass."""
    env = {k: v for k, v in os.environ.items() if not any(h in k.upper() for h in SECRET_HINTS)}
    env["COLUMNS"] = "300"
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rfE", "-p", "no:cacheprovider", "tests"]
    try:
        p = subprocess.run(cmd, cwd=round_dir, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"pytest timed out after {timeout}s"
    lines = [ln[:300] for ln in p.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    if p.returncode == 0:
        return 0, ""
    if p.returncode == 5:
        return 5, "pytest collected no tests"
    return p.returncode, "\n".join(lines) or f"pytest exited with code {p.returncode}"


@dataclass
class TaskState:
    task_id: str
    ticket: str
    contract: str
    user: str | None
    round: int = 1
    engineer_files: dict = field(default_factory=dict)
    tester_files: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)  # role -> files for the current round
    rejected: list = field(default_factory=list)
    done: bool = False


def make_orchestrator() -> Agent:
    kwargs = {}
    if os.getenv("ORCHESTRATOR_PORT"):
        kwargs["port"] = int(os.environ["ORCHESTRATOR_PORT"])
    agent = Agent(
        name="orchestrator",
        seed=os.getenv("ORCHESTRATOR_SEED"),
        mailbox=os.getenv("USE_MAILBOX") == "1",
        report_events=os.getenv("REPORT_EVENTS", "1") == "1",
        readme_path=os.getenv("ORCHESTRATOR_README", "orchestrator_README.md"),
        description=(
            "Give me a small coding task. Two independent agents (Engineer and Tester) "
            "work on it in parallel without seeing each other's work; pytest decides pass or fail."
        ),
        **kwargs,
    )
    engineer_addr = os.environ["ENGINEER_ADDRESS"]
    tester_addr = os.environ["TESTER_ADDRESS"]
    role_addr = {"engineer": engineer_addr, "tester": tester_addr}
    max_rounds = int(os.getenv("MAX_ROUNDS", "3"))
    pytest_timeout = int(os.getenv("PYTEST_TIMEOUT", "60"))
    workspace = Path(os.getenv("WORKSPACE_DIR", "workspace"))
    tasks: dict[str, TaskState] = {}
    chat_proto = Protocol(spec=chat_protocol_spec)

    async def notify(ctx: Context, st: TaskState, text: str, final: bool = False):
        ctx.logger.info(f"[{st.task_id}] {text}")
        log_event("progress", task_id=st.task_id, text=text)
        if st.user:
            content = [TextContent(text=text)] + ([EndSessionContent()] if final else [])
            await ctx.send(st.user, ChatMessage(content=content))

    async def send_logged(ctx: Context, dest: str, msg, **extra):
        log_event("send", to=dest, type=type(msg).__name__, **extra)
        await ctx.send(dest, msg)

    async def start_task(ctx: Context, ticket: str, user: str | None) -> TaskState:
        task_id = uuid.uuid4().hex[:8]
        st = TaskState(task_id, ticket, CONTRACT_TEMPLATE.format(ticket=ticket), user)
        tasks[task_id] = st
        (workspace / task_id).mkdir(parents=True, exist_ok=True)
        (workspace / task_id / "contract.txt").write_text(st.contract, encoding="utf-8")
        log_event("task_created", task_id=task_id, ticket=ticket, user=user)
        await asyncio.gather(
            *(
                send_logged(
                    ctx, role_addr[r], TaskAssigned(task_id=task_id, role=r, round=1, contract=st.contract),
                    task_id=task_id, role=r, round=1,
                )
                for r in ("engineer", "tester")
            )
        )
        return st

    @chat_proto.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        text = msg.text().strip()
        log_event("chat_in", sender=sender, text=text)
        if not text:
            return
        st = await start_task(ctx, text, sender)
        await notify(ctx, st, f"Working on it (task {st.task_id}). Engineer and Tester are starting in parallel.")

    @chat_proto.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        log_event("chat_ack", sender=sender, acked=str(msg.acknowledged_msg_id))

    agent.include(chat_proto, publish_manifest=True)

    @agent.on_message(Submission)
    async def on_submission(ctx: Context, sender: str, msg: Submission):
        st = tasks.get(msg.task_id)
        log_event(
            "submission_in", sender=sender, task_id=msg.task_id, role=msg.role, round=msg.round,
            files={p: len(c) for p, c in msg.files.items()}, notes=msg.notes,
            assumptions=msg.assumptions,
        )
        if msg.role not in role_addr or sender != role_addr[msg.role]:
            ctx.logger.warning(f"ignored Submission: sender does not match role {msg.role}")
            return
        if st is None or st.done or msg.round != st.round or msg.role in st.pending:
            ctx.logger.warning(f"ignored stale/duplicate Submission {msg.task_id} {msg.role} r{msg.round}")
            return
        if msg.round > 1 and msg.role == "tester":
            return  # tester keeps its round-1 tests
        good = {}
        for path, content in msg.files.items():
            err = check_path(msg.role, path)
            if err:
                st.rejected.append(f"{path}: {err}")
                log_event("path_rejected", task_id=st.task_id, role=msg.role, path=path, reason=err)
                ctx.logger.warning(f"[{st.task_id}] rejected {msg.role} file {path!r}: {err}")
            else:
                good[path] = content
        st.pending[msg.role] = good
        sub_dir = workspace / st.task_id / "submissions"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / f"r{msg.round}_{msg.role}.json").write_text(
            json.dumps({
                "round": msg.round, "role": msg.role, "notes": msg.notes,
                "assumptions": msg.assumptions, "files": msg.files,
                "rejected": [r for r in st.rejected if r.split(":")[0] in msg.files],
            }),
            encoding="utf-8",
        )
        await notify(ctx, st, f"{msg.role.capitalize()} submitted round {msg.round} ({len(good)} file(s)).")
        needed = {"engineer", "tester"} if st.round == 1 else {"engineer"}
        if needed <= st.pending.keys():
            await evaluate(ctx, st)

    async def evaluate(ctx: Context, st: TaskState):
        st.engineer_files.update(st.pending.get("engineer", {}))
        if "tester" in st.pending:
            st.tester_files = st.pending["tester"]
        st.pending = {}
        round_dir = workspace / st.task_id / f"round_{st.round}"
        shutil.rmtree(round_dir, ignore_errors=True)
        for path, content in {**st.tester_files, **st.engineer_files}.items():
            target = (round_dir / path).resolve()
            if not target.is_relative_to(round_dir.resolve()):
                continue  # defence in depth; check_path already rejects these
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        await notify(ctx, st, f"Running tests for round {st.round}.")
        code, report = await asyncio.to_thread(run_pytest, round_dir, pytest_timeout)
        log_event("pytest", task_id=st.task_id, round=st.round, exit_code=code, report=report)
        if code == 0:
            st.done = True
            log_event("decision", task_id=st.task_id, round=st.round, outcome="pass")
            await notify(ctx, st, f"PASS: all tests passed in round {st.round}. Files: {round_dir}", final=True)
            return
        if st.round >= max_rounds:
            st.done = True
            log_event("decision", task_id=st.task_id, round=st.round, outcome="fail_final")
            await notify(
                ctx, st,
                f"FAIL: tests still failing after {st.round} round(s) (pytest exit {code}).\n{report}",
                final=True,
            )
            return
        if st.rejected:
            report += "\nRejected paths:\n" + "\n".join(st.rejected)
        st.round += 1
        log_event("decision", task_id=st.task_id, round=st.round, outcome="retry")
        await notify(ctx, st, f"Tests failed (pytest exit {code}). Sending feedback to the Engineer for round {st.round}.")
        await send_logged(
            ctx, engineer_addr, Feedback(task_id=st.task_id, round=st.round, report=report),
            task_id=st.task_id, role="engineer", round=st.round, report=report,
        )

    @agent.on_event("startup")
    async def on_startup(ctx: Context):
        ctx.logger.info(f"orchestrator address: {agent.address}")
        ticket = os.getenv("STARTUP_TICKET")
        if ticket:
            await asyncio.sleep(1)
            await start_task(ctx, ticket, None)

    return agent


if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()
    os.environ["USE_MAILBOX"] = "1"
    # Python 3.14 no longer creates a default event loop; uagents 0.26.1 expects one.
    asyncio.set_event_loop(asyncio.new_event_loop())
    agent = make_orchestrator()
    print(f"orchestrator address: {agent.address}")
    agent.run()
