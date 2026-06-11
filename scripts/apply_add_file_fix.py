"""Apply add_file fix: atomic INSERT OR REPLACE instead of TOCTOU get+insert."""
import pathlib
import shutil
import datetime
import ast

TARGET = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database_client/client_api_files.py"
)


def main():
    lines = TARGET.read_text(encoding="utf-8").splitlines(keepends=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_suffix(f".py.bak_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"Backup: {backup}")
    new_body = [
        "        result = self.execute(\n",
        "            \"INSERT OR REPLACE INTO files \"\n",
        "            \"(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) \"\n",
        "            \"VALUES (?, ?, ?, ?, ?, ?, 0, ?)\",\n",
        "            (\n",
        "                project_id,\n",
        "                abs_path,\n",
        "                str(relative_path),\n",
        "                lines,\n",
        "                last_modified,\n",
        "                1 if has_docstring else 0,\n",
        "                watch_dir_id,\n",
        "            ),\n",
        "        )\n",
        "        row_id = result.get(\"lastrowid\") if result else None\n",
        "        if row_id is None:\n",
        "            existing = self.get_file_by_path(abs_path, project_id)\n",
        "            if existing:\n",
        "                return str(existing[\"id\"])\n",
        "            raise ValueError(\n",
        "                f\"INSERT OR REPLACE into files did not return a row id for {abs_path}\"\n",
        "            )\n",
        "        return str(row_id)\n",
    ]
    lines[131] = "        Uses atomic INSERT OR REPLACE to avoid TOCTOU race between get and insert.\n"
    new_lines = lines[:153] + new_body + lines[184:]
    TARGET.write_text("".join(new_lines), encoding="utf-8")
    print(f"Done. Lines: {len(new_lines)}")
    ast.parse(TARGET.read_text())
    print("Syntax OK")


if __name__ == "__main__":
    main()
