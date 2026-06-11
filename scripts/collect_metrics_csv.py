"""
Collect quantitative metrics every 10 minutes for 1 hour and append to CSV.

Uses direct SQLite queries so it works regardless of server/driver. Writes to
data/metrics_YYYYMMDD.csv with columns: datetime_utc, datetime_iso, files_total,
files_active, files_indexed, files_indexed_pct, files_needing_indexing,
files_needing_chunking, chunks_total, chunks_vectorized, chunks_vectorized_pct,
db_size_mb, indexing_worker_operation, vectorization_worker_operation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_db_path() -> Path:
    """Resolve database path from config.json."""
    config_path = PROJECT_ROOT / "config.json"
    if not config_path.exists():
        return PROJECT_ROOT / "data" / "ai_editor.db"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Resolve via storage_paths if available
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from ai_editor.core.storage_paths import (
            load_raw_config,
            resolve_storage_paths,
        )

        config_data = load_raw_config(str(config_path))
        storage = resolve_storage_paths(
            config_data=config_data, config_path=str(config_path)
        )
        return storage.db_path
    except Exception:
        pass
    data_dir = config.get("ai_editor", {}).get("data_dir") or "data"
    return PROJECT_ROOT / data_dir / "ai_editor.db"


def read_worker_operation(status_path: Path) -> str:
    """Read current_operation from worker status JSON; return empty string if missing."""
    if not status_path or not status_path.exists():
        return ""
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("current_operation", ""))
    except Exception:
        return ""


def collect_row(conn: sqlite3.Connection, db_path: Path, logs_dir: Path) -> list:
    """Run queries and return one row (list of values) for CSV."""
    now = datetime.now(timezone.utc)
    datetime_iso = now.isoformat()
    datetime_utc = now.strftime("%Y-%m-%d %H:%M:%S")

    cur = conn.execute("SELECT COUNT(*) FROM files")
    files_total = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM files WHERE deleted = 1")
    deleted = cur.fetchone()[0]
    files_active = files_total - deleted

    cur = conn.execute(
        "SELECT COUNT(*) FROM files WHERE (deleted = 0 OR deleted IS NULL) "
        "AND (needs_chunking = 0 OR needs_chunking IS NULL)"
    )
    files_indexed = cur.fetchone()[0]
    files_indexed_pct = (
        round((files_indexed / files_active * 100), 2) if files_active else 0
    )

    cur = conn.execute(
        "SELECT COUNT(*) FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1"
    )
    files_needing_indexing = cur.fetchone()[0]

    cur = conn.execute(
        "SELECT COUNT(DISTINCT f.id) FROM files f "
        "WHERE (f.deleted = 0 OR f.deleted IS NULL) "
        "AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)"
    )
    files_needing_chunking = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM code_chunks")
    chunks_total = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NOT NULL")
    chunks_vectorized = cur.fetchone()[0]
    chunks_vectorized_pct = (
        round((chunks_vectorized / chunks_total * 100), 2) if chunks_total else 0
    )

    db_size_mb = 0.0
    if db_path.exists():
        db_size_mb = round(db_path.stat().st_size / (1024 * 1024), 2)

    idx_status = logs_dir / "indexing_worker.status.json"
    vec_status = logs_dir / "vectorization_worker.status.json"
    indexing_operation = read_worker_operation(idx_status)
    vectorization_operation = read_worker_operation(vec_status)

    return [
        datetime_utc,
        datetime_iso,
        files_total,
        files_active,
        files_indexed,
        files_indexed_pct,
        files_needing_indexing,
        files_needing_chunking,
        chunks_total,
        chunks_vectorized,
        chunks_vectorized_pct,
        db_size_mb,
        indexing_operation,
        vectorization_operation,
    ]


HEADER = [
    "datetime_utc",
    "datetime_iso",
    "files_total",
    "files_active",
    "files_indexed",
    "files_indexed_pct",
    "files_needing_indexing",
    "files_needing_chunking",
    "chunks_total",
    "chunks_vectorized",
    "chunks_vectorized_pct",
    "db_size_mb",
    "indexing_worker_operation",
    "vectorization_worker_operation",
]


def main() -> int:
    """Run 6 collections, 10 minutes apart, appending to data/metrics_YYYYMMDD.csv."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect metrics to CSV every 10 min for 1 hour"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Append one snapshot and exit (no 10-min loop)",
    )
    args = parser.parse_args()
    iterations = 1 if args.once else 6

    db_path = get_db_path()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    # Logs dir for worker status files
    logs_dir = PROJECT_ROOT / "logs"
    if not logs_dir.exists():
        logs_dir = PROJECT_ROOT / "log"

    csv_path = (
        PROJECT_ROOT / "data" / f"metrics_{datetime.now().strftime('%Y%m%d')}.csv"
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()

    for iteration in range(iterations):
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                row = collect_row(conn, db_path, logs_dir)
            finally:
                conn.close()

            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if write_header:
                    w.writerow(HEADER)
                    write_header = False
                w.writerow(row)
            print(f"[{row[0]}] files_indexed={row[4]} chunks_vectorized={row[9]}")

        except Exception as e:
            print(f"Error at iteration {iteration + 1}: {e}", file=sys.stderr)

        if iteration < iterations - 1:
            time.sleep(600)  # 10 minutes

    print(f"Done. CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
