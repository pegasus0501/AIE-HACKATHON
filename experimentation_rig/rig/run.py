"""Run an engineer patch and a tester suite on a throwaway clone of the repo and database."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import common, workspace
from .snapshot import path_for

PYTEST_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider
python_files = test_*.py
"""


@dataclass
class RunResult:
    passed: bool
    failures: list = field(default_factory=list)
    work_db: str | None = None
    before_db: str | None = None
    tests: dict = field(default_factory=dict)  # test name -> passed | failed | error | skipped
    stage: str = "tests"
    output: str = ""
    work_dir: str | None = None

    def cleanup(self) -> None:
        if self.work_dir:
            common.rmtree(Path(self.work_dir))
            self.work_dir = None
            self.work_db = None
            self.before_db = None


def _clean_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_") and k not in ("DATABASE_PATH",)}
    env.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra)
    return env


def _write_files(repo: Path, files: dict) -> None:
    for name, text in files.items():
        target = repo / name.replace("\\", "/")
        if not common.inside(repo, target):
            raise ValueError(f"path escapes the clone: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


_ASSERT = re.compile(r"assert\s+(.+?)\s*==\s*(.+)", re.DOTALL)


def _parse_junit(path: Path) -> tuple[dict, list]:
    tests, failures = {}, []
    if not path.exists():
        return tests, failures
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        name = case.get("name", "?")
        bad = case.find("failure")
        err = case.find("error")
        skipped = case.find("skipped")
        if bad is None and err is None:
            tests[name] = "skipped" if skipped is not None else "passed"
            continue
        node = bad if bad is not None else err
        tests[name] = "failed" if bad is not None else "error"
        message = (node.get("message") or "").strip()
        body = (node.text or "").strip()
        m = _ASSERT.search(message) or _ASSERT.search(body)
        failures.append({
            "test": name,
            "message": message[:800],
            "input": None,
            "expected": m.group(2).strip()[:200] if m else None,
            "actual": m.group(1).strip()[:200] if m else None,
        })
    return tests, failures


def run_in_clone(ticket_id: str, engineer_files: dict, tester_files: dict, *, keep_db: bool = False,
                 base_repo: Path | None = None, with_truth: bool = False) -> RunResult:
    """Apply engineer_files and tester_files to a clone of the pristine repo, migrate a copy of the
    snapshot, run pytest in isolation, and report. The clone is deleted unless keep_db is True."""
    common.check_ticket(ticket_id)
    workspace.validate_paths(engineer_files, "engineer")
    workspace.validate_paths(tester_files, "tester")
    base_repo = Path(base_repo or common.TEMPLATE_DIR)
    source_db = path_for(ticket_id)

    work = common.WORK_DIR / f"{ticket_id}-{uuid.uuid4().hex[:8]}"
    repo = work / "repo"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base_repo, repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
    _write_files(repo, engineer_files)
    _write_files(repo, tester_files)
    work_db, before_db = work / "work.db", work / "before.db"
    shutil.copyfile(source_db, work_db)
    shutil.copyfile(source_db, before_db)
    common.make_writable(work_db)
    common.make_readonly(before_db)
    (work / "pytest.ini").write_text(PYTEST_INI, encoding="utf-8")
    (repo / "pytest.ini").write_text(PYTEST_INI, encoding="utf-8")

    extra = {"DATABASE_PATH": str(work_db), "BASELINE_DATABASE_PATH": str(before_db), "PYTHONPATH": str(repo)}
    if with_truth and common.TRUTH_DB.exists():
        extra["RIG_TRUTH_DB"] = str(common.TRUTH_DB)
    env = _clean_env(extra)
    result = RunResult(passed=False, work_db=str(work_db), before_db=str(before_db), work_dir=str(work))
    try:
        # 1. apply pending migrations to the work copy
        mig = subprocess.run([sys.executable, "-m", "src.migrate", "up"], cwd=repo, env=env,
                             capture_output=True, text=True, timeout=common.RUN_TIMEOUT)
        if mig.returncode != 0:
            result.stage = "migrate"
            result.output = (mig.stdout + mig.stderr)[-4000:]
            result.failures = [{"test": "migrations", "message": result.output[-800:],
                                "input": None, "expected": None, "actual": None}]
            return result
        # 2. pytest, isolated from any ini, conftest or plugin outside the clone
        junit = work / "junit.xml"
        cmd = [sys.executable, "-m", "pytest", "-c", str(work / "pytest.ini"), "--rootdir", str(repo),
               "--confcutdir", str(repo), "-p", "no:cacheprovider", "-q", "--tb=short",
               f"--junitxml={junit}", "tests"]
        try:
            proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True,
                                  timeout=common.RUN_TIMEOUT)
            result.output = (proc.stdout + proc.stderr)[-6000:]
            code = proc.returncode
        except subprocess.TimeoutExpired:
            result.stage = "timeout"
            result.failures = [{"test": "suite", "message": f"timed out after {common.RUN_TIMEOUT}s",
                                "input": None, "expected": None, "actual": None}]
            return result
        result.tests, result.failures = _parse_junit(junit)
        result.passed = code == 0 and bool(result.tests)
        if code not in (0, 1) and not result.failures:
            result.failures = [{"test": "suite", "message": result.output[-800:],
                                "input": None, "expected": None, "actual": None}]
        return result
    finally:
        if not keep_db:
            result.cleanup()
