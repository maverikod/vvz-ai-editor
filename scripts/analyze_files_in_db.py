"""
Analyze files table: breakdown by .venv, deleted, path patterns, duplicates.

Helps find why file count is high (e.g. 6000+). Run from project root.
Uses direct SQLite to data/ai_editor.db (no RPC driver needed).

Usage:
  python scripts/analyze_files_in_db.py
  python scripts/analyze_files_in_db.py --db data/ai_editor.db

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def get_db_path(config_path: str = "config.json") -> Path:
    """Read db_path from ai_editor.db_path in config.json."""
    path = Path(config_path)
    if not path.exists():
        return Path("data/ai_editor.db")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        db_path = (data.get("ai_editor") or {}).get(
            "db_path"
        ) or "data/ai_editor.db"
        return Path(db_path)
    except Exception:
        return Path("data/ai_editor.db")


def run_analysis(conn: sqlite3.Connection) -> None:
    """Run all analysis queries and print breakdown."""
    cur = conn.cursor()

    # Total files and chunks (for comparison: "6000" might be chunks)
    cur.execute("SELECT COUNT(*) FROM files")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM code_chunks")
    chunks_total = cur.fetchone()[0]
    print("=== FILES TABLE ANALYSIS ===")
    print(f"Total files:  {total}")
    print(f"Total chunks: {chunks_total}\n")

    if total == 0:
        return

    # Deleted
    cur.execute("SELECT COUNT(*) FROM files WHERE deleted = 1")
    deleted = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM files WHERE deleted = 0 OR deleted IS NULL")
    active = cur.fetchone()[0]
    print("By deleted flag:")
    print(f"  deleted = 1:     {deleted}")
    print(f"  active (0/NULL): {active}\n")

    # Path patterns (case-sensitive and LIKE)
    patterns = [
        (".venv", "path LIKE '%.venv%'"),
        ("venv/", "path LIKE '%/venv/%' OR path LIKE '%\\venv\\%'"),
        ("__pycache__", "path LIKE '%__pycache__%'"),
        ("node_modules", "path LIKE '%node_modules%'"),
        (".pytest_cache", "path LIKE '%.pytest_cache%'"),
        (".mypy_cache", "path LIKE '%.mypy_cache%'"),
        (".git/", "path LIKE '%.git/%'"),
        ("/build/", "path LIKE '%/build/%'"),
        ("/dist/", "path LIKE '%/dist/%'"),
        ("egg-info", "path LIKE '%egg-info%'"),
    ]
    print("By path pattern (active only):")
    for name, where in patterns:
        cur.execute(
            f"SELECT COUNT(*) FROM files WHERE (deleted = 0 OR deleted IS NULL) AND ({where})"
        )
        n = cur.fetchone()[0]
        if n > 0:
            print(f"  {name:20} {n}")
    cur.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE (deleted = 0 OR deleted IS NULL)
          AND path NOT LIKE '%.venv%'
          AND path NOT LIKE '%/venv/%'
          AND path NOT LIKE '%__pycache__%'
          AND path NOT LIKE '%node_modules%'
          AND path NOT LIKE '%.pytest_cache%'
          AND path NOT LIKE '%.mypy_cache%'
          AND path NOT LIKE '%.git/%'
          AND path NOT LIKE '%/build/%'
          AND path NOT LIKE '%/dist/%'
          AND path NOT LIKE '%egg-info%'
        """
    )
    other = cur.fetchone()[0]
    print(f"  {'(none of above)':20} {other}\n")

    # By project
    cur.execute(
        """
        SELECT p.id, p.name, p.root_path, COUNT(f.id) AS cnt
        FROM projects p
        LEFT JOIN files f ON f.project_id = p.id AND (f.deleted = 0 OR f.deleted IS NULL)
        GROUP BY p.id
        ORDER BY cnt DESC
        LIMIT 20
        """
    )
    rows = cur.fetchall()
    print("By project (top 20, active files):")
    for row in rows:
        pid, name, root, cnt = row
        print(f"  {cnt:6}  {name or pid or '?'}  {root or ''}")
    print()

    # Duplicates: same (project_id, path)
    cur.execute(
        """
        SELECT project_id, path, COUNT(*) AS cnt
        FROM files
        WHERE (deleted = 0 OR deleted IS NULL)
        GROUP BY project_id, path
        HAVING COUNT(*) > 1
        """
    )
    dup_rows = cur.fetchall()
    dup_pairs = sum(r[2] for r in dup_rows)
    dup_extra = dup_pairs - len(dup_rows) if dup_pairs else 0
    print("Duplicates (same project_id + path, active):")
    print(f"  duplicate (project_id, path) groups: {len(dup_rows)}")
    print(f"  total rows in those groups: {dup_pairs}")
    print(f"  extra rows (could be removed): {dup_extra}")
    if dup_rows and len(dup_rows) <= 10:
        for row in dup_rows:
            print(f"    {row[2]}x  {row[1]}")
    elif dup_rows:
        for row in dup_rows[:5]:
            print(f"    {row[2]}x  {row[1]}")
        print(f"    ... and {len(dup_rows) - 5} more")
    print()

    # Sample of .venv / venv paths
    cur.execute(
        """
        SELECT path FROM files
        WHERE (deleted = 0 OR deleted IS NULL)
          AND (path LIKE '%.venv%' OR path LIKE '%/venv/%')
        LIMIT 15
        """
    )
    samples = [r[0] for r in cur.fetchall()]
    if samples:
        print("Sample paths (.venv / venv):")
        for s in samples:
            print(f"  {s}")
    print()

    # Paths that look like they might be under test_data vs rest
    cur.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE (deleted = 0 OR deleted IS NULL) AND path LIKE '%/test_data/%'
        """
    )
    test_data_count = cur.fetchone()[0]
    print(f"Paths containing '/test_data/': {test_data_count}")
    cur.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE (deleted = 0 OR deleted IS NULL) AND path NOT LIKE '%/test_data/%'
        """
    )
    not_test_data = cur.fetchone()[0]
    print(f"Paths not containing '/test_data/': {not_test_data}\n")

    # Optional: count paths that no longer exist on disk (when total not huge)
    if total <= 2000:
        cur.execute("SELECT path FROM files WHERE (deleted = 0 OR deleted IS NULL)")
        paths = [r[0] for r in cur.fetchall()]
        missing_list = [p for p in paths if p and not Path(p).exists()]
        missing = len(missing_list)
        if missing > 0:
            print(f"Paths that do not exist on disk: {missing}")
            for p in missing_list[:20]:
                print(f"  {p[:100]}")
            if missing > 20:
                print(f"  ... and {missing - 20} more")
        else:
            print("All active file paths exist on disk.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze files table breakdown")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite DB (default: from config.json or data/ai_editor.db)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Config path to read db_path from",
    )
    args = parser.parse_args()
    db_path = args.db or get_db_path(str(args.config))
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        run_analysis(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
