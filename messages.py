from uagents import Model


class TaskAssigned(Model):
    task_id: str
    role: str  # "engineer" or "tester"
    round: int
    contract: str
    ticket: str = ""  # rig ticket id (e.g. "exp1"); empty for free-form tasks


class Submission(Model):
    task_id: str
    role: str
    round: int
    files: dict[str, str]  # path -> full file contents
    notes: str = ""
    assumptions: list[str] = []
    pushback: list[dict[str, str]] = []  # non-blocking doubts: {"point", "question"}


class Feedback(Model):
    task_id: str
    round: int  # the round the engineer should now produce
    report: str  # failing test names + assertion lines only, never test source


class PushBack(Model):
    """An agent refuses to guess: it asks about a vague requirement and waits for answers."""

    task_id: str
    role: str
    round: int
    items: list[dict[str, str]]  # {"point", "question"}


class Clarification(Model):
    task_id: str
    round: int
    answers: list[dict[str, str]]  # {"question", "answer"}
