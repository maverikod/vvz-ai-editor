#!/usr/bin/env python3
"""
Standalone pipeline runner: start server, then client (mcp-proxy-adapter) polls it.

Flow: start ai-editor-server -> run MCP suites (client calls server via
mcp-proxy-adapter JsonRpcClient) -> stop server -> report.
Runs suite logic in-process (no pytest). Exit code 0 if all pass, 1 otherwise.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure repo root is on path when run as script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.pipeline.config import PipelineConfig
from scripts.pipeline.reporting import TestReporter
from scripts.pipeline.server_manager import ServerManager
from scripts.pipeline.test_mcp_commands_skeleton import run_suite as run_skeleton_suite
from scripts.pipeline.test_mcp_commands_db_project_file import (
    run_suite as run_db_project_file_suite,
)
from scripts.pipeline.test_mcp_commands_db_other import run_suite as run_db_other_suite


def _log(msg: str) -> None:
    """Print state to stdout so user sees progress."""
    print(msg, flush=True)


def run_pipeline() -> int:
    """Run pipeline: start server, run MCP suites, stop server, report. Return 0 on success, 1 on failure."""
    config = PipelineConfig()
    reporter = TestReporter()
    server_manager = ServerManager(config)
    suites = [
        ("scripts/pipeline/test_mcp_commands_skeleton.py", run_skeleton_suite),
        (
            "scripts/pipeline/test_mcp_commands_db_project_file.py",
            run_db_project_file_suite,
        ),
        ("scripts/pipeline/test_mcp_commands_db_other.py", run_db_other_suite),
    ]

    _log("[pipeline] started")
    _log(f"[pipeline] config: timeout={config.timeout}s, suites={len(suites)}")
    _log(
        "[pipeline] steps: start server -> client (mcp-proxy-adapter) polls server -> stop -> report"
    )
    reporter.start_pipeline()
    failed_suites: list[str] = []

    try:
        # 1) Start ai-editor-server
        _log("[pipeline] --- server startup ---")
        _log("[pipeline] creating test config, applying DB schema, starting daemon...")
        reporter.start_suite("Server Startup")
        start_time = time.time()
        started = server_manager.start_server()
        if not started:
            _log("[pipeline] server start failed, retrying restart...")
            started = server_manager.restart_server(timeout=config.timeout)
        elapsed = time.time() - start_time
        if started:
            reporter.add_test_result(
                "server_start",
                "passed",
                elapsed,
                message="Real ai-editor-server started successfully",
            )
            _log(f"[pipeline] server started OK ({elapsed:.1f}s)")
        else:
            reporter.add_test_result(
                "server_start",
                "failed",
                elapsed,
                error="Failed to start server",
            )
            reporter.end_suite()
            _log("[pipeline] server startup FAILED")
            return 1
        reporter.end_suite()

        # 2) Client (mcp-proxy-adapter) polls server: run MCP suites in-process
        _log("[pipeline] --- MCP command suites (client polls server) ---")
        reporter.start_suite("MCP Command Suites")
        for idx, (suite_name, run_fn) in enumerate(suites, 1):
            _log(f"[pipeline] suite {idx}/{len(suites)}: {suite_name}")
            start_time = time.time()
            try:
                run_fn()
                elapsed = time.time() - start_time
                reporter.add_test_result(
                    suite_name,
                    "passed",
                    elapsed,
                    message="Suite completed",
                )
                _log(f"[pipeline]   passed ({elapsed:.1f}s)")
            except Exception as exc:
                elapsed = time.time() - start_time
                err_msg = str(exc)
                reporter.add_test_result(
                    suite_name,
                    "failed",
                    elapsed,
                    error=err_msg,
                )
                failed_suites.append(suite_name)
                _log(f"[pipeline]   FAILED ({elapsed:.1f}s): {err_msg}")
                _log("[pipeline] stop on first error")
                break
        reporter.end_suite()
    finally:
        _log("[pipeline] --- teardown ---")
        _log("[pipeline] stopping server...")
        server_manager.stop_server()
        _log("[pipeline] server stopped")

    _log("[pipeline] --- report ---")
    report = reporter.end_pipeline()
    _log("[pipeline] writing summary to stdout...")
    reporter.print_summary(report)
    json_path = reporter.save_report(report, format="json")
    html_path = reporter.save_report(report, format="html")
    _log(f"[pipeline] report saved: {json_path.name}, {html_path.name}")

    if failed_suites:
        _log(f"[pipeline] FAILED suites: {', '.join(failed_suites)}")
        _log("[pipeline] exit 1")
        return 1
    _log("[pipeline] all passed, exit 0")
    return 0


def main() -> int:
    return run_pipeline()


if __name__ == "__main__":
    sys.exit(main())
