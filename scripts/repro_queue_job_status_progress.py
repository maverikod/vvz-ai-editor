#!/usr/bin/env python3
"""
Reproduce bug: queue_get_job_status does not return progress/description
updated by the running job (LongRunningJob or CommandExecutionJob).

Steps:
1. Add a long_running job (duration=12s) that calls set_progress/set_description.
2. Start the job and poll queue_get_job_status every 2s.
3. If progress stays 0 and description stays initial -> BUG REPRODUCED.

Note: To try spawn mode, start the server with:
  python scripts/run_server_spawn.py --config ... --port 8080
If the bug still does not appear, reproduce in the consumer environment
(ai-editor-server with spawn and CommandExecutionJob).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import sys
import time
import uuid

import requests

PORT = 8080
BASE = f"http://localhost:{PORT}"


def jsonrpc(method: str, params: dict, req_id: int = 1) -> dict:
    r = requests.post(
        f"{BASE}/api/jsonrpc",
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result", {})


def main() -> int:
    job_id = f"repro_{uuid.uuid4().hex[:8]}"
    print("Reproduce: queue_get_job_status progress/description not updated")
    print(f"Job ID: {job_id}")
    print()

    # 1. Add long_running job (updates progress every second, 12 steps)
    print("1. Adding long_running job (duration=12s, updates progress each second)...")
    try:
        jsonrpc(
            "queue_add_job",
            {
                "job_type": "long_running",
                "job_id": job_id,
                "params": {"duration": 12, "task_type": "repro_task"},
            },
        )
    except Exception as e:
        print(f"   ERROR: {e}")
        return 2
    print("   OK")

    # 2. Start job
    print("2. Starting job...")
    try:
        jsonrpc("queue_start_job", {"job_id": job_id})
    except Exception as e:
        print(f"   ERROR: {e}")
        return 2
    print("   OK")

    # 3. Poll queue_get_job_status every 2s (job runs 12s, so we see several polls)
    num_polls = 7
    poll_interval = 2
    progress_values = []
    descriptions = []
    print(f"3. Polling queue_get_job_status {num_polls} times (every {poll_interval}s)...")
    for i in range(num_polls):
        time.sleep(poll_interval)
        try:
            res = jsonrpc("queue_get_job_status", {"job_id": job_id}, req_id=100 + i)
        except Exception as e:
            print(f"   Poll {i+1} ERROR: {e}")
            continue
        data = res.get("data", res)
        status = data.get("status", "?")
        progress = data.get("progress", 0)
        desc = (data.get("description") or "").strip()
        progress_values.append(progress)
        descriptions.append(desc)
        print(f"   [{i+1}/{num_polls}] status={status} progress={progress}%  description={desc!r}")
        if status in ("completed", "failed", "error", "stopped"):
            print("   Job finished.")
            break

    # 4. Conclusion
    print()
    progress_changed = len(progress_values) > 1 and (
        any(p != progress_values[0] for p in progress_values) or progress_values[0] != 0
    )
    desc_changed = len(descriptions) > 1 and any(
        d != (descriptions[0] or "") for d in descriptions
    )

    if not progress_changed and not desc_changed:
        print("BUG REPRODUCED: progress and description never changed in queue_get_job_status")
        print("  (Job runs and calls set_progress/set_description, but API returns initial values.)")
        return 1
    if not progress_changed:
        print("PARTIAL: progress never changed in queue_get_job_status")
        return 1
    if not desc_changed:
        print("PARTIAL: description never changed in queue_get_job_status")
        return 1
    print("OK: progress and/or description updated in queue_get_job_status (bug not present here)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
