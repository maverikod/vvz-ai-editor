"""
Configuration validation failure reporting for main entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List


def report_validation_failure(
    validation_results: List[Any],
    summary: Dict[str, Any],
    full_config: Dict[str, Any],
    config_path: Path,
) -> None:
    """
    Log validation errors/warnings and exit with code 1.

    Tries to use log file from config if available; otherwise prints to stderr.
    """
    errors = [r for r in validation_results if r.level == "error"]
    warnings = [r for r in validation_results if r.level == "warning"]

    log_dir = None
    log_file = None
    logger = None

    try:
        server_config = full_config.get("server", {})
        log_dir_str = server_config.get("log_dir", "./logs")
        log_dir = Path(log_dir_str)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "mcp_server.log"

        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stderr),
            ],
            force=True,
        )
        logger = logging.getLogger(__name__)
    except Exception:
        log_dir = None
        log_file = None
        logger = None

    error_header = "❌ Configuration validation failed:"
    if logger:
        logger.error(error_header)
    else:
        print(error_header, file=sys.stderr)

    for error in errors:
        section_info = (
            f" ({error.section}" + (f".{error.key}" if error.key else "") + ")"
            if error.section
            else ""
        )
        error_msg = f"   - {error.message}{section_info}"
        if error.suggestion:
            error_msg += f" - {error.suggestion}"

        if logger:
            logger.error(error_msg)
        else:
            print(error_msg, file=sys.stderr)

    if warnings:
        warning_header = "⚠️  Warnings:"
        if logger:
            logger.warning(warning_header)
        else:
            print(warning_header, file=sys.stderr)

        for warning in warnings:
            section_info = (
                f" ({warning.section}"
                + (f".{warning.key}" if warning.key else "")
                + ")"
                if warning.section
                else ""
            )
            warning_msg = f"   - {warning.message}{section_info}"
            if warning.suggestion:
                warning_msg += f" - {warning.suggestion}"

            if logger:
                logger.warning(warning_msg)
            else:
                print(warning_msg, file=sys.stderr)

    if logger and log_file:
        print(
            f"\n❌ Configuration validation failed. See log file: {log_file}",
            file=sys.stderr,
        )
    else:
        print(
            f"\n❌ Configuration validation failed: "
            f"{summary['errors']} error(s), {summary['warnings']} warning(s)",
            file=sys.stderr,
        )

    sys.exit(1)
