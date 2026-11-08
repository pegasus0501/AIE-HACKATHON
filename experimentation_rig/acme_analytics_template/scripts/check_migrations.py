"""Exit with status 1 if any migration is missing its up or down script."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.migrate import discover  # noqa: E402


def main() -> int:
    missing = []
    for version, parts in discover().items():
        for direction in ("up", "down"):
            if direction not in parts:
                missing.append(f"{version}_{parts['name']}.{direction}.sql")
    if missing:
        print("missing migration files:")
        for name in missing:
            print("  ", name)
        return 1
    print("all migrations have up and down scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
