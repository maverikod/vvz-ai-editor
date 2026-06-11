#!/usr/bin/env python3
"""
Monitor vectorization progress and speed (chunks/sec, queue size).

Uses DatabaseClient (socket to driver) to get vectorization_stats and chunk counts.
Run while the server and vectorization worker are running.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import sys
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_editor.core.constants import DEFAULT_DB_DRIVER_SOCKET_DIR
from ai_editor.core.database_client.client import DatabaseClient


def main() -> None:
    db_path = Path("data/ai_editor.db")
    if not db_path.exists():
        db_path = Path(__file__).resolve().parent.parent / "data" / "ai_editor.db"
    db_name = db_path.stem
    socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
    socket_path = str(socket_dir / f"{db_name}_driver.sock")
    if not Path(socket_path).exists():
        print(f"Socket not found: {socket_path}. Is the server running?")
        sys.exit(1)

    client = DatabaseClient(socket_path=socket_path)
    client.connect()

    try:
        # Chunk counts
        r = client.execute(
            "SELECT COUNT(*) AS n FROM code_chunks WHERE vector_id IS NULL",
            (),
        )
        data = r.get("data", []) if isinstance(r, dict) else []
        pending = int(data[0].get("n", 0)) if data else 0

        r2 = client.execute(
            "SELECT COUNT(*) AS n FROM code_chunks WHERE vector_id IS NOT NULL",
            (),
        )
        data2 = r2.get("data", []) if isinstance(r2, dict) else []
        done = int(data2[0].get("n", 0)) if data2 else 0

        total = pending + done
        pct = (100.0 * done / total) if total else 0

        # Vectorization cycle stats: prefer last COMPLETED cycle for speed (has final counts)
        stats_completed = None
        stats_active = None
        try:
            q_completed = """
            SELECT cycle_id, cycle_start_time, cycle_end_time,
                   chunks_total_at_start, chunks_processed, chunks_skipped, chunks_failed,
                   files_total_at_start, files_vectorized,
                   total_processing_time_seconds, average_processing_time_seconds, last_updated
            FROM vectorization_stats
            WHERE cycle_end_time IS NOT NULL
            ORDER BY cycle_start_time DESC LIMIT 1
            """
            r3 = client.execute(q_completed, ())
            rows = r3.get("data", []) if isinstance(r3, dict) else []
            if rows:
                stats_completed = dict(rows[0])
            q_active = """
            SELECT cycle_id, chunks_total_at_start, chunks_processed, chunks_skipped, chunks_failed,
                   total_processing_time_seconds
            FROM vectorization_stats
            WHERE cycle_end_time IS NULL
            ORDER BY cycle_start_time DESC LIMIT 1
            """
            r4 = client.execute(q_active, ())
            rows4 = r4.get("data", []) if isinstance(r4, dict) else []
            if rows4:
                stats_active = dict(rows4[0])
        except Exception:
            pass

        # Worker status file
        status_path = Path("logs/vectorization_worker.status.json")
        if not status_path.is_absolute():
            status_path = (
                Path(__file__).resolve().parent.parent
                / "logs"
                / "vectorization_worker.status.json"
            )
        op = "?"
        if status_path.exists():
            try:
                data = json.loads(status_path.read_text())
                op = data.get("current_operation", "?")
            except Exception:
                pass

        print("=== Vectorization monitor ===")
        print(
            f"  Chunks: {done} vectorized, {pending} pending (total {total}) — {pct:.1f}%"
        )
        print(f"  Worker status: {op}")

        # Prefer completed cycle for speed (real totals and duration)
        stats = stats_completed or stats_active
        if stats:
            chunks_processed = int(stats.get("chunks_processed") or 0)
            chunks_failed = int(stats.get("chunks_failed") or 0)
            chunks_skipped = int(stats.get("chunks_skipped") or 0)
            total_at_start = int(stats.get("chunks_total_at_start") or 0)
            total_sec = stats.get("total_processing_time_seconds")
            avg_sec = stats.get("average_processing_time_seconds")
            # Speed from completed cycle: chunks per second
            if total_sec is not None and float(total_sec) > 0 and chunks_processed > 0:
                speed = chunks_processed / float(total_sec)
                print(
                    f"  Last cycle: processed={chunks_processed}, failed={chunks_failed}, "
                    f"skipped={chunks_skipped} (start queue={total_at_start})"
                )
                print(
                    f"  Speed: {speed:.2f} chunks/sec (cycle time {float(total_sec):.1f} s)"
                )
            elif avg_sec and float(avg_sec) > 0:
                speed = 1.0 / float(avg_sec)
                print(
                    f"  Cycle: processed={chunks_processed}, failed={chunks_failed}, "
                    f"skipped={chunks_skipped}, total_at_start={total_at_start}"
                )
                print(
                    f"  Speed: {speed:.2f} chunks/sec (avg {float(avg_sec):.2f} s/chunk)"
                )
            else:
                print(
                    f"  Cycle: processed={chunks_processed}, failed={chunks_failed}, "
                    f"skipped={chunks_skipped}, total_at_start={total_at_start}"
                )
                if total_sec is not None:
                    print(f"  Total cycle time: {total_sec:.1f} s")
            if stats_active and not stats_completed:
                print("  (current cycle in progress; speed after it completes)")
        else:
            print("  Cycle stats: (no completed or active cycle)")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
