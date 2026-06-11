"""
Remove extracted schema/migration bodies from base.py and keep only delegation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BASE_PY = BASE / "ai_editor" / "core" / "database" / "base.py"

REPLACEMENT = '''
    def _migrate_to_uuid_projects(self) -> None:
        """Migrate projects table from INTEGER to UUID4 if needed."""
        run_migrate_to_uuid_projects(self)

    def _migrate_schema(self) -> None:
        """
        Migrate database schema - add missing columns, update structure.
        Called on every database initialization to ensure schema is up to date.
        """
        run_migrate_schema(self)

'''


def main() -> None:
    lines = BASE_PY.read_text(encoding="utf-8").splitlines(keepends=True)
    # Find "def _create_schema_REMOVED_BLOCK_START" and "def close"
    start_i = None
    close_i = None
    for i, line in enumerate(lines):
        if "def _create_schema_REMOVED_BLOCK_START" in line:
            start_i = i
        if start_i is not None and "def close(self)" in line:
            close_i = i
            break
    if start_i is None or close_i is None:
        raise SystemExit("Could not find block boundaries")
    new_content = "".join(lines[:start_i]) + REPLACEMENT + "".join(lines[close_i:])
    BASE_PY.write_text(new_content, encoding="utf-8")
    print("Trimmed base.py")


if __name__ == "__main__":
    main()
