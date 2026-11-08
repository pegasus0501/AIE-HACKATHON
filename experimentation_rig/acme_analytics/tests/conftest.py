import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import connect, database_path  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    """A private copy of the configured database, so tests may write freely."""
    target = tmp_path / "copy.db"
    shutil.copyfile(database_path(), target)
    return str(target)


@pytest.fixture
def conn(db_path):
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def baseline_path():
    """Path of a read-only copy of the database taken before the change under test, if provided."""
    value = os.environ.get("BASELINE_DATABASE_PATH")
    if not value:
        pytest.skip("BASELINE_DATABASE_PATH is not set")
    return value
