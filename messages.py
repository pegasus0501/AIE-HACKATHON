from uagents import Model


class TaskAssigned(Model):
    task_id: str
    role: str  # "engineer" or "tester"
    round: int
    contract: str


class Submission(Model):
    task_id: str
    role: str
    round: int
    files: dict[str, str]  # path -> full file contents
    notes: str = ""
    assumptions: list[str] = []


class Feedback(Model):
    task_id: str
    round: int  # the round the engineer should now produce
    report: str  # failing test names + assertion lines only, never test source
