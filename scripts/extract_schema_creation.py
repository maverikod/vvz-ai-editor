"""
Extract schema creation and migration from base.py into schema_creation.py.
Reads base.py, extracts _create_schema, _migrate_to_uuid_projects, _migrate_schema
as functions with db parameter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BASE_PY = BASE / "ai_editor" / "core" / "database" / "base.py"
OUT_PY = BASE / "ai_editor" / "core" / "database" / "schema_creation.py"


def transform_body(lines: list[str], is_create_schema: bool = False) -> list[str]:
    """Remove 4-space method indent, replace self with db; fix migration calls in create_schema."""
    out = []
    for line in lines:
        # Method body was 8 spaces (body) or 4 (try/except); reduce by 4 so function body is 4/0
        if line.startswith("        "):
            line = "    " + line[8:]
        elif line.startswith("    "):
            line = "    " + line[4:]
        else:
            line = "    " + line if line.strip() else line
        line = line.replace("self._execute", "db._execute")
        line = line.replace("self._commit", "db._commit")
        line = line.replace("self._fetchone", "db._fetchone")
        line = line.replace("self._fetchall", "db._fetchall")
        line = line.replace("self._get_table_info", "db._get_table_info")
        if is_create_schema:
            line = line.replace(
                "self._migrate_to_uuid_projects()", "run_migrate_to_uuid_projects(db)"
            )
            line = line.replace("self._migrate_schema()", "run_migrate_schema(db)")
        out.append(line)
    return out


def main() -> None:
    text = BASE_PY.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Line numbers 1-based: _create_schema 497-1055, _migrate_to_uuid 1056-1141, _migrate_schema 1142-1451
    create_schema_lines = lines[497:1055]  # 498-1055 inclusive -> index 497 to 1055
    migrate_uuid_lines = lines[1055:1141]  # 1056-1141
    migrate_schema_lines = lines[1141:1451]  # 1142-1451

    # Drop "def _create_schema(self) -> None:" and docstring from first block
    create_body = []
    skip_until_blank = False
    for i, line in enumerate(create_schema_lines):
        if "def _create_schema(self)" in line:
            skip_until_blank = True
            continue
        if skip_until_blank:
            if line.strip().startswith('"""') or (line.strip() == '"""'):
                continue
            if line.strip() and not line.strip().startswith('"""'):
                skip_until_blank = False
            else:
                continue
        create_body.append(line)

    migrate_uuid_body = []
    skip = False
    for line in migrate_uuid_lines:
        if "def _migrate_to_uuid_projects(self)" in line:
            skip = True
            continue
        if skip and (line.strip().startswith('"""') or line.strip() == '"""'):
            continue
        if skip and line.strip() == "":
            continue
        if skip and line.strip().startswith("#"):
            skip = False
        migrate_uuid_body.append(line)

    migrate_schema_body = []
    skip = False
    for line in migrate_schema_lines:
        if "def _migrate_schema(self)" in line:
            skip = True
            continue
        if skip and ('"""' in line or line.strip().startswith("This method")):
            continue
        if skip and line.strip() == "":
            continue
        if skip and line.strip().startswith("# Use driver"):
            skip = False
        migrate_schema_body.append(line)

    create_out = transform_body(create_body, is_create_schema=True)
    uuid_out = transform_body(migrate_uuid_body, is_create_schema=False)
    schema_out = transform_body(migrate_schema_body, is_create_schema=False)

    header = '''"""
Schema creation and migrations for CodeDatabase.
Extracted from base.py to keep file size under limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_create_schema(db: Any) -> None:
    """Create database schema if it doesn't exist."""
'''

    uuid_header = '''
def run_migrate_to_uuid_projects(db: Any) -> None:
    """Migrate projects table from INTEGER to UUID4 if needed."""
'''

    schema_header = '''
def run_migrate_schema(db: Any) -> None:
    """
    Migrate database schema - add missing columns, update structure.
    Called on every database initialization to ensure schema is up to date.
    """
'''

    result = [header]
    result.extend(create_out)
    result.append(uuid_header)
    result.extend(uuid_out)
    result.append(schema_header)
    result.extend(schema_out)

    OUT_PY.write_text("".join(result), encoding="utf-8")
    print("Written", OUT_PY)


if __name__ == "__main__":
    main()
