"""Fix _FILES_INSERT_OR_REPLACE_NORM: remove deleted=0 to avoid bool adaptation mismatch."""
import pathlib
import shutil
import datetime
import ast

CLIENT = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_client/client_api_files.py"
)
PG = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_driver_pkg/drivers/postgres_run.py"
)

NEW_SQL = (
    "INSERT OR REPLACE INTO files "
    "(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


def patch_client(lines):
    """Remove deleted=0 from execute() call in add_file."""
    result = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        # Remove the "deleted" column from INSERT
        if '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "' in line:
            result.append(line.replace(
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "',
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "'
            ))
            continue
        # Remove "VALUES (?, ?, ?, ?, ?, ?, 0, ?)"
        if '"VALUES (?, ?, ?, ?, ?, ?, 0, ?)",' in line:
            result.append(line.replace(
                '"VALUES (?, ?, ?, ?, ?, ?, 0, ?)",',
                '"VALUES (?, ?, ?, ?, ?, ?, ?)",'
            ))
            continue
        # Remove the "1 if has_docstring else 0," line followed by watch_dir_id
        # Actually we need to remove the `0,` param for deleted
        # The params tuple is: project_id, abs_path, str(relative_path), lines, last_modified,
        #                      1 if has_docstring else 0, watch_dir_id
        # We already have that - deleted(0) was between has_docstring and watch_dir_id
        # The line "                1 if has_docstring else 0," - keep it (it's has_docstring)
        # There was no separate "0," line for deleted in our original patch
        # Let's check: we put deleted hardcoded as 0 in VALUES not as param
        result.append(line)
    return result


def patch_pg(lines):
    """Update _FILES_INSERT_OR_REPLACE_NORM and its handler branch."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Fix the norm constant
        if '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "' in line:
            result.append(line.replace(
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "',
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "'
            ))
            i += 1
            continue
        if '"VALUES (?, ?, ?, ?, ?, ?, 0, ?)"' in line and '_FILES_INSERT_OR_REPLACE_NORM' not in lines[max(0,i-5):i+1]:
            # This is inside _FILES_INSERT_OR_REPLACE_NORM constant definition
            result.append(line.replace(
                '"VALUES (?, ?, ?, ?, ?, ?, 0, ?)"',
                '"VALUES (?, ?, ?, ?, ?, ?, ?)"'
            ))
            i += 1
            continue
        # Fix the ON CONFLICT branch: remove deleted line from SET
        if '"deleted = EXCLUDED.deleted, "' in line:
            i += 1  # skip this line
            continue
        # Fix VALUES in the ON CONFLICT branch
        if '"VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) "' in line:
            result.append(line.replace(
                '"VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) "',
                '"VALUES (?, ?, ?, ?, ?, ?, ?) "'
            ))
            i += 1
            continue
        # Fix column list in ON CONFLICT INSERT INTO
        if '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "' in line:
            result.append(line.replace(
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "',
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "'
            ))
            i += 1
            continue
        result.append(line)
        i += 1
    return result


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Patch client
    lines = CLIENT.read_text(encoding="utf-8").splitlines(keepends=True)
    shutil.copy2(CLIENT, CLIENT.with_suffix(f".py.bak2_{ts}"))
    new_lines = patch_client(lines)
    CLIENT.write_text("".join(new_lines), encoding="utf-8")
    ast.parse(CLIENT.read_text())
    print("client_api_files.py: Syntax OK")

    # Patch postgres_run
    lines = PG.read_text(encoding="utf-8").splitlines(keepends=True)
    shutil.copy2(PG, PG.with_suffix(f".py.bak2_{ts}"))
    new_lines = patch_pg(lines)
    PG.write_text("".join(new_lines), encoding="utf-8")
    ast.parse(PG.read_text())
    print("postgres_run.py: Syntax OK")
    print("Done")


if __name__ == "__main__":
    main()
