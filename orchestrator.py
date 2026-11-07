import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
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
from llm import answer_questions
from messages import Clarification, Feedback, PushBack, Submission, TaskAssigned

ALLOWED = {"engineer": ("migrations/", "queries/", "src/"), "tester": ("tests/",)}
SECRET_HINTS = ("KEY", "SEED", "TOKEN", "SECRET", "PASSWORD")
LIST_WORDS = {"issues", "list", "list issues", "/issues", "help", "?"}
ISSUE_ID = re.compile(r"\bexp\d\b", re.I)
FILLER = re.compile(r"\b(run|start|work|on|issue|issues|and|please|the)\b|[\s,;:+&-]+", re.I)

# Free-form tasks only. Rig tickets use the rig's own ticket and contract.
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


def make_title(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s|\n", text.strip(), maxsplit=1)[0].strip().rstrip(".")
    return first if len(first) <= 60 else first[:59] + "…"


def parse_command(text: str) -> tuple[str, list[str]]:
    """('list', []) | ('run', [ticket ids]) | ('free', [])."""
    t = text.strip().lower()
    if t in LIST_WORDS:
        return "list", []
    ids = list(dict.fromkeys(i.lower() for i in ISSUE_ID.findall(text)))
    if ids and not FILLER.sub("", ISSUE_ID.sub("", t)):
        return "run", ids
    return "free", []


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


def score_line(rep: dict) -> str:
    return (
        f"Score: the Tester caught {rep['caught']}/{rep['total']} planted problems ({rep['catch_rate']:.0%}); "
        f"false alarms: {len(rep['false_alarms'])}; "
        f"Engineer passes the hidden tests: {'yes' if rep['engineer_passes_hidden_tests'] else 'no'}."
    )


@dataclass
class TaskState:
    task_id: str
    title: str
    ticket: str
    contract: str  # what the agents were given
    full_contract: str  # what the Orchestrator answers questions from
    user: str | None
    ticket_id: str = ""  # rig ticket id, empty for free-form tasks
    round: int = 1
    engineer_files: dict = field(default_factory=dict)
    tester_files: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)  # role -> files for the current round
    rejected: list = field(default_factory=list)
    asked: set = field(default_factory=set)  # roles that already used their one pushback exchange
    last_activity: float = field(default_factory=time.time)
    busy: bool = False
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
            "List the open issues, pick one, and watch two independent agents (Engineer and Tester) work on it "
            "in parallel, push back on vague requirements, and be scored. Say 'issues' to start."
        ),
        **kwargs,
    )
    engineer_addr = os.environ["ENGINEER_ADDRESS"]
    tester_addr = os.environ["TESTER_ADDRESS"]
    role_addr = {"engineer": engineer_addr, "tester": tester_addr}
    max_rounds = int(os.getenv("MAX_ROUNDS", "3"))
    pytest_timeout = int(os.getenv("PYTEST_TIMEOUT", "60"))
    task_timeout = int(os.getenv("TASK_TIMEOUT", "900"))
    # "on_pushback": agents get only the vague ticket; the contract is released as answers to their questions.
    # "upfront": agents get ticket + contract immediately (the rig's documented usage).
    contract_mode = os.getenv("CONTRACT_MODE", "on_pushback")
    workspace = Path(os.getenv("WORKSPACE_DIR", "workspace"))
    tasks: dict[str, TaskState] = {}
    chat_proto = Protocol(spec=chat_protocol_spec)

    async def reply(ctx: Context, user: str | None, text: str, final: bool = False):
        if user:
            content = [TextContent(text=text)] + ([EndSessionContent()] if final else [])
            await ctx.send(user, ChatMessage(content=content))

    async def notify(ctx: Context, st: TaskState, text: str, final: bool = False):
        ctx.logger.info(f"[{st.task_id}] {text}")
        log_event("progress", task_id=st.task_id, text=text)
        await reply(ctx, st.user, text, final)

    async def send_logged(ctx: Context, dest: str, msg, **extra):
        log_event("send", to=dest, type=type(msg).__name__, **extra)
        await ctx.send(dest, msg)

    async def start_task(ctx: Context, text: str, user: str | None, ticket_id: str = "") -> TaskState:
        task_id = uuid.uuid4().hex[:8]
        if ticket_id:
            import rig_bridge

            ticket = rig_bridge.ticket_text(ticket_id)
            title = rig_bridge.title(ticket_id)
            full = f"{ticket}\n\n{rig_bridge.contract_text(ticket_id)}"
            contract = full if contract_mode == "upfront" else ticket
        else:
            ticket, title = text, make_title(text)
            contract = full = CONTRACT_TEMPLATE.format(ticket=text)
        st = TaskState(task_id, title, ticket, contract, full, user, ticket_id)
        tasks[task_id] = st
        (workspace / task_id).mkdir(parents=True, exist_ok=True)
        (workspace / task_id / "contract.txt").write_text(contract, encoding="utf-8")
        log_event("task_created", task_id=task_id, title=title, ticket=ticket, ticket_id=ticket_id,
                  contract_mode=contract_mode if ticket_id else "template", user=user)
        await asyncio.gather(
            *(
                send_logged(
                    ctx, role_addr[r],
                    TaskAssigned(task_id=task_id, role=r, round=1, contract=contract, ticket=ticket_id),
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
        kind, ids = parse_command(text)
        if kind != "free":
            import rig_bridge

            if kind == "list":
                lines = [f"{i['id']}: {i['title']}" for i in rig_bridge.issues()]
                await reply(ctx, sender, "Open issues:\n" + "\n".join(lines)
                            + "\n\nReply with an issue id (or several, e.g. exp1 exp2) to start. "
                              "Or describe a new task in your own words.")
                return
            bad = [i for i in ids if not rig_bridge.is_issue(i)]
            if bad:
                await reply(ctx, sender, f"I don't have an issue called {', '.join(bad)}. Say 'issues' to list them.")
                return
            for tid in ids:
                st = await start_task(ctx, "", sender, tid)
                await notify(ctx, st, f"Working on '{st.title}' (task {st.task_id}). Engineer and Tester are starting in parallel.")
            return
        st = await start_task(ctx, text, sender)
        await notify(ctx, st, f"Working on it (task {st.task_id}). Engineer and Tester are starting in parallel.")

    @chat_proto.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        log_event("chat_ack", sender=sender, acked=str(msg.acknowledged_msg_id))

    agent.include(chat_proto, publish_manifest=True)

    def valid_sender(sender: str, role: str) -> bool:
        return role in role_addr and sender == role_addr[role]

    @agent.on_message(PushBack)
    async def on_pushback(ctx: Context, sender: str, msg: PushBack):
        st = tasks.get(msg.task_id)
        log_event("pushback", sender=sender, task_id=msg.task_id, role=msg.role, round=msg.round, items=msg.items)
        if not valid_sender(sender, msg.role) or st is None or st.done or msg.role in st.asked:
            ctx.logger.warning(f"ignored PushBack {msg.task_id} {msg.role}")
            return
        st.asked.add(msg.role)
        st.last_activity = time.time()
        questions = [i.get("question", "") for i in msg.items]
        await notify(ctx, st, f"{msg.role.capitalize()} pushed back on the requirement: {questions[0][:120]}"
                              + (f" (+{len(questions) - 1} more)" if len(questions) > 1 else ""))
        answers = await asyncio.to_thread(answer_questions, st.full_contract, questions)
        qa = [{"question": q, "answer": a} for q, a in zip(questions, answers)]
        log_event("clarification", task_id=st.task_id, role=msg.role, round=msg.round, answers=qa)
        st.last_activity = time.time()
        await send_logged(
            ctx, role_addr[msg.role], Clarification(task_id=st.task_id, round=msg.round, answers=qa),
            task_id=st.task_id, role=msg.role, round=msg.round, answers=qa,
        )
        await notify(ctx, st, f"Answered the {msg.role}'s questions from the approved contract.")

    @agent.on_message(Submission)
    async def on_submission(ctx: Context, sender: str, msg: Submission):
        st = tasks.get(msg.task_id)
        log_event(
            "submission_in", sender=sender, task_id=msg.task_id, role=msg.role, round=msg.round,
            files={p: len(c) for p, c in msg.files.items()}, notes=msg.notes,
            assumptions=msg.assumptions, pushback=msg.pushback,
        )
        if not valid_sender(sender, msg.role):
            ctx.logger.warning(f"ignored Submission: sender does not match role {msg.role}")
            return
        if st is None or st.done or msg.round != st.round or msg.role in st.pending:
            ctx.logger.warning(f"ignored stale/duplicate Submission {msg.task_id} {msg.role} r{msg.round}")
            return
        if msg.round > 1 and msg.role == "tester":
            return  # tester keeps its round-1 tests
        st.last_activity = time.time()
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
                "assumptions": msg.assumptions, "pushback": msg.pushback, "files": msg.files,
                "rejected": [r for r in st.rejected if r.split(":")[0] in msg.files],
            }),
            encoding="utf-8",
        )
        await notify(ctx, st, f"{msg.role.capitalize()} submitted round {msg.round} ({len(good)} file(s)).")
        needed = {"engineer", "tester"} if st.round == 1 else {"engineer"}
        if needed <= st.pending.keys():
            await evaluate(ctx, st)

    async def finish(ctx: Context, st: TaskState, outcome: str, headline: str):
        st.done = True
        log_event("decision", task_id=st.task_id, round=st.round, outcome=outcome)
        extra = ""
        if st.ticket_id:
            import rig_bridge

            await notify(ctx, st, "Scoring against the rig's hidden tests and planted problems.")
            st.busy = True
            try:
                rep = await asyncio.to_thread(rig_bridge.score, st.ticket_id, st.engineer_files, st.tester_files)
                (workspace / st.task_id / "score.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
                log_event("score", task_id=st.task_id, report=rep)
                extra = "\n" + score_line(rep)
            except Exception as e:  # keep the verdict even if scoring breaks
                log_event("score_error", task_id=st.task_id, error=f"{type(e).__name__}: {str(e)[:300]}")
                extra = f"\n(scoring failed: {type(e).__name__})"
            finally:
                st.busy = False
        await notify(ctx, st, headline + extra, final=True)

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
        st.busy = True
        try:
            if st.ticket_id:
                import rig_bridge

                res = await asyncio.to_thread(rig_bridge.run_round, st.ticket_id, st.engineer_files, st.tester_files)
                code, report = (0, "") if res["passed"] else (1, res["report"] or "tests did not pass")
            else:
                code, report = await asyncio.to_thread(run_pytest, round_dir, pytest_timeout)
        finally:
            st.busy = False
        st.last_activity = time.time()
        log_event("pytest", task_id=st.task_id, round=st.round, exit_code=code, report=report)
        if code == 0:
            await finish(ctx, st, "pass", f"PASS: all tests passed in round {st.round}. Files: {round_dir}")
            return
        if st.round >= max_rounds:
            await finish(ctx, st, "fail_final",
                         f"FAIL: tests still failing after {st.round} round(s) (exit {code}).\n{report}")
            return
        if st.rejected:
            report += "\nRejected paths:\n" + "\n".join(st.rejected)
        st.round += 1
        log_event("decision", task_id=st.task_id, round=st.round, outcome="retry")
        await notify(ctx, st, f"Tests failed (exit {code}). Sending feedback to the Engineer for round {st.round}.")
        await send_logged(
            ctx, engineer_addr, Feedback(task_id=st.task_id, round=st.round, report=report),
            task_id=st.task_id, role="engineer", round=st.round, report=report,
        )

    @agent.on_interval(period=20.0)
    async def watchdog(ctx: Context):
        now = time.time()
        for st in list(tasks.values()):
            if st.done or st.busy or now - st.last_activity < task_timeout:
                continue
            waiting = [r for r in (("engineer", "tester") if st.round == 1 else ("engineer",)) if r not in st.pending]
            st.done = True
            log_event("decision", task_id=st.task_id, round=st.round, outcome="timeout", waiting=waiting)
            await notify(ctx, st, f"FAIL: no response from {', '.join(waiting) or 'an agent'} for {task_timeout}s. Giving up.",
                         final=True)

    @agent.on_event("startup")
    async def on_startup(ctx: Context):
        ctx.logger.info(f"orchestrator address: {agent.address}")
        ticket = os.getenv("STARTUP_TICKET")
        if ticket:
            await asyncio.sleep(1)
            kind, ids = parse_command(ticket)
            if kind == "run":
                for tid in ids:
                    await start_task(ctx, "", None, tid)
            else:
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
