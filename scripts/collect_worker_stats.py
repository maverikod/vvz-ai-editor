"""
Script to collect worker and database statistics over time.

Collects statistics every minute for 30 minutes using MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ai_editor.commands.worker_status_mcp_commands import (
    GetDatabaseStatusMCPCommand,
    GetWorkerStatusMCPCommand,
)


class StatisticsCollector:
    """Collect statistics from workers and database."""

    def __init__(self, root_dir: str, output_file: str):
        """
        Initialize statistics collector.

        Args:
            root_dir: Root directory of the project
            output_file: Path to output JSON file for statistics
        """
        self.root_dir = Path(root_dir).resolve()
        self.output_file = Path(output_file)
        self.stats: List[Dict[str, Any]] = []
        self.worker_status_cmd = GetWorkerStatusMCPCommand()
        self.db_status_cmd = GetDatabaseStatusMCPCommand()

    async def collect_snapshot(self) -> Dict[str, Any]:
        """
        Collect a single snapshot of statistics.

        Returns:
            Dictionary with timestamp and statistics
        """
        snapshot: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "workers": {},
            "database": {},
        }

        # Collect worker statuses
        for worker_type in ["file_watcher", "vectorization"]:
            try:
                result = await self.worker_status_cmd.execute(
                    worker_type=worker_type,
                    log_path=str(self.root_dir / "logs" / f"{worker_type}.log"),
                )
                if hasattr(result, "data") and result.data:
                    snapshot["workers"][worker_type] = result.data
                else:
                    snapshot["workers"][worker_type] = {"error": "No data returned"}
            except Exception as e:
                snapshot["workers"][worker_type] = {"error": str(e)}

        # Collect database status
        try:
            result = await self.db_status_cmd.execute(root_dir=str(self.root_dir))
            if hasattr(result, "data") and result.data:
                snapshot["database"] = result.data
            else:
                snapshot["database"] = {"error": "No data returned"}
        except Exception as e:
            snapshot["database"] = {"error": str(e)}

        return snapshot

    async def run(self, duration_minutes: int = 30, interval_seconds: int = 60):
        """
        Run statistics collection.

        Args:
            duration_minutes: Total duration in minutes
            interval_seconds: Interval between collections in seconds
        """
        total_iterations = (duration_minutes * 60) // interval_seconds
        print(f"Starting statistics collection:")
        print(f"  Duration: {duration_minutes} minutes")
        print(f"  Interval: {interval_seconds} seconds")
        print(f"  Total snapshots: {total_iterations}")
        print(f"  Output file: {self.output_file}")
        print()

        for i in range(total_iterations):
            print(
                f"[{i+1}/{total_iterations}] Collecting snapshot...",
                end=" ",
                flush=True,
            )
            try:
                snapshot = await self.collect_snapshot()
                self.stats.append(snapshot)

                # Print summary
                workers_info = []
                for worker_type, data in snapshot["workers"].items():
                    if "error" not in data:
                        pid = data.get("pid", "N/A")
                        alive = data.get("alive", False)
                        workers_info.append(f"{worker_type}: PID {pid}, alive={alive}")
                    else:
                        workers_info.append(f"{worker_type}: ERROR")

                db_info = "N/A"
                if "error" not in snapshot["database"]:
                    db_data = snapshot["database"]
                    file_size = db_data.get("file_size_mb", 0)
                    total_files = db_data.get("files", {}).get("total", 0)
                    total_chunks = db_data.get("chunks", {}).get("total", 0)
                    db_info = f"DB: {file_size:.2f}MB, files: {total_files}, chunks: {total_chunks}"

                print(f"OK - {' | '.join(workers_info)} | {db_info}")

                # Save intermediate results
                self.save_stats()

            except Exception as e:
                print(f"ERROR: {e}")
                self.stats.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e),
                    }
                )

            # Wait before next collection (except for last iteration)
            if i < total_iterations - 1:
                await asyncio.sleep(interval_seconds)

        print()
        print(f"Collection complete. Total snapshots: {len(self.stats)}")
        print(f"Statistics saved to: {self.output_file}")

    def save_stats(self):
        """Save statistics to JSON file."""
        output_data = {
            "collection_start": self.stats[0]["timestamp"] if self.stats else None,
            "collection_end": self.stats[-1]["timestamp"] if self.stats else None,
            "total_snapshots": len(self.stats),
            "snapshots": self.stats,
        }
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w") as f:
            json.dump(output_data, f, indent=2)


async def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    root_dir = str(project_root)
    output_file = project_root / "data" / "worker_statistics.json"

    collector = StatisticsCollector(root_dir=root_dir, output_file=output_file)
    await collector.run(duration_minutes=30, interval_seconds=60)


if __name__ == "__main__":
    asyncio.run(main())
