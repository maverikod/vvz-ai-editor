"""Add _FILES_INSERT_OR_REPLACE_NORM constant and handler to postgres_run.py."""
import pathlib
import shutil
import datetime
import ast

TARGET = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_driver_pkg/drivers/postgres_run.py"
)


def main():
    src = TARGET.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_suffix(f".py.bak_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"Backup: {backup}")

    # 1. Find line with _FUNCTIONS_INSERT_OR_REPLACE_NORM assignment (starts with that name)
    func_norm_line = next(
        i for i, l in enumerate(lines)
        if l.strip().startswith("_FUNCTIONS_INSERT_OR_REPLACE_NORM")
    )
    # Find end of that assignment (closing paren on its own line)
    end_assign = func_norm_line
    while not lines[end_assign].rstrip().endswith(")"):
        end_assign += 1
    print(f"_FUNCTIONS_INSERT_OR_REPLACE_NORM ends at line {end_assign + 1}")

    # 2. Insert _FILES_INSERT_OR_REPLACE_NORM after it
    files_norm = [
        "\n",
        "_FILES_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(\n",
        "    \"INSERT OR REPLACE INTO files \"\n",
        "    \"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) \"\n",
        "    \"VALUES (?, ?, ?, ?, ?, ?, 0, ?)\"\n",
        ")\n",
    ]
    lines = lines[: end_assign + 1] + files_norm + lines[end_assign + 1 :]
    print("Inserted _FILES_INSERT_OR_REPLACE_NORM constant")

    # 3. Find the last `if norm ==` branch before `return s` in _adapt_sqlite_dml_for_postgres
    # and insert a new branch after it.
    # Find `return s` at the end of the function (last line of _adapt_sqlite_dml_for_postgres)
    return_s_line = next(
        i for i, l in reversed(list(enumerate(lines)))
        if l.strip() == "return s"
    )
    print(f"'return s' at line {return_s_line + 1}")

    files_branch = [
        "    if norm == _FILES_INSERT_OR_REPLACE_NORM:\n",
        "        return (\n",
        "            \"INSERT INTO files \"\n",
        "            \"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) \"\n",
        "            \"VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) \"\n",
        "            \"ON CONFLICT (project_id, path) DO UPDATE SET \"\n",
        "            \"path = EXCLUDED.path, \"\n",
        "            \"relative_path = EXCLUDED.relative_path, \"\n",
        "            \"lines = EXCLUDED.lines, \"\n",
        "            \"last_modified = EXCLUDED.last_modified, \"\n",
        "            \"has_docstring = EXCLUDED.has_docstring, \"\n",
        "            \"deleted = EXCLUDED.deleted, \"\n",
        "            \"watch_dir_id = EXCLUDED.watch_dir_id\"\n",
        "        )\n",
    ]
    lines = lines[:return_s_line] + files_branch + lines[return_s_line:]
    print("Inserted _FILES branch in _adapt_sqlite_dml_for_postgres")

    TARGET.write_text("".join(lines), encoding="utf-8")
    print(f"Done. Lines: {len(lines)}")
    ast.parse(TARGET.read_text())
    print("Syntax OK")


if __name__ == "__main__":
    main()
