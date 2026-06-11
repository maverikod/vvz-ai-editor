"""Fix files norm v2: restore client from backup then apply clean patch."""
import pathlib
import shutil
import datetime
import ast
import glob

CLIENT = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_client/client_api_files.py"
)
PG = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_driver_pkg/drivers/postgres_run.py"
)


def restore_client():
    """Restore client from bak2 backup (before fix_files_norm ran)."""
    backups = sorted(glob.glob(str(CLIENT.parent / (CLIENT.stem + ".py.bak2_*"))))
    if not backups:
        raise FileNotFoundError("No bak2 backup found for client_api_files.py")
    latest = backups[-1]
    shutil.copy2(latest, CLIENT)
    print(f"Restored client from {latest}")


def patch_client_clean(lines):
    """Replace the execute() block to remove deleted=0 from VALUES.

    The block currently is (with 8-col indent):
        result = self.execute(
            "INSERT OR REPLACE INTO files "
            "(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (
                project_id,
                abs_path,
                str(relative_path),
                lines,
                last_modified,
                1 if has_docstring else 0,
                watch_dir_id,
            ),
        )
    We replace it removing 'deleted, ' from column list, '0, ?' -> '?' in VALUES.
    """
    # Find the line with INSERT OR REPLACE INTO files inside add_file
    start = None
    for i, line in enumerate(lines):
        if ('"INSERT OR REPLACE INTO files "' in line
                and i > 100):  # skip if it's in postgres_run norms
            start = i
            break
    if start is None:
        raise ValueError("Could not find INSERT OR REPLACE INTO files in client")
    print(f"Found INSERT at line {start + 1}")

    new_block = [
        '        result = self.execute(\n',
        '            "INSERT OR REPLACE INTO files "\n',
        '            "(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "\n',
        '            "VALUES (?, ?, ?, ?, ?, ?, ?)",\n',
        '            (\n',
        '                project_id,\n',
        '                abs_path,\n',
        '                str(relative_path),\n',
        '                lines,\n',
        '                last_modified,\n',
        '                1 if has_docstring else 0,\n',
        '                watch_dir_id,\n',
        '            ),\n',
        '        )\n',
    ]

    # Find end of the execute() block (closing ')\n' at 8-col indent)
    end = start
    depth = 0
    for i in range(start - 1, len(lines)):
        for ch in lines[i]:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
        if depth == 0 and i >= start:
            end = i
            break
    print(f"execute() block: lines {start} - {end + 1}")

    return lines[:start - 1] + new_block + lines[end + 1:]


def patch_pg_clean(lines):
    """Fix _FILES_INSERT_OR_REPLACE_NORM and its handler in postgres_run.py."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Fix norm constant: remove deleted from column list
        if ('_FILES_INSERT_OR_REPLACE_NORM' in line
                and 'deleted' not in line
                and i + 3 < len(lines)
                and 'deleted' in lines[i + 1]):
            # The deleted column line is i+1
            result.append(line)
            i += 1
            # Skip line with deleted column
            result.append(
                lines[i].replace(
                    '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "',
                    '"(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "'
                )
            )
            i += 1
            continue
        # Fix VALUES in norm constant
        if ('"VALUES (?, ?, ?, ?, ?, ?, 0, ?)"' in line
                and '_FILES_INSERT_OR_REPLACE_NORM' in ''.join(lines[max(0, i-5):i])):
            result.append(line.replace(
                '"VALUES (?, ?, ?, ?, ?, ?, 0, ?)"',
                '"VALUES (?, ?, ?, ?, ?, ?, ?)"'
            ))
            i += 1
            continue
        # Fix ON CONFLICT branch column list
        if ('"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "' in line
                and 'INSERT INTO files' in ''.join(lines[max(0, i-2):i])):
            result.append(line.replace(
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "',
                '"(project_id, path, relative_path, lines, last_modified, has_docstring, watch_dir_id) "'
            ))
            i += 1
            continue
        # Fix VALUES in ON CONFLICT branch
        if '"VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) "' in line:
            result.append(line.replace(
                '"VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) "',
                '"VALUES (?, ?, ?, ?, ?, ?, ?) "'
            ))
            i += 1
            continue
        # Remove deleted from ON CONFLICT SET
        if '"deleted = EXCLUDED.deleted, "' in line:
            i += 1
            continue
        result.append(line)
        i += 1
    return result


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Restore and re-patch client
    restore_client()
    lines = CLIENT.read_text(encoding="utf-8").splitlines(keepends=True)
    shutil.copy2(CLIENT, CLIENT.with_suffix(f".py.bak3_{ts}"))
    new_lines = patch_client_clean(lines)
    CLIENT.write_text("".join(new_lines), encoding="utf-8")
    ast.parse(CLIENT.read_text())
    print(f"client_api_files.py: Syntax OK, {len(new_lines)} lines")

    # Patch postgres_run
    lines = PG.read_text(encoding="utf-8").splitlines(keepends=True)
    shutil.copy2(PG, PG.with_suffix(f".py.bak3_{ts}"))
    new_lines = patch_pg_clean(lines)
    PG.write_text("".join(new_lines), encoding="utf-8")
    ast.parse(PG.read_text())
    print(f"postgres_run.py: Syntax OK, {len(new_lines)} lines")
    print("Done")


if __name__ == "__main__":
    main()
