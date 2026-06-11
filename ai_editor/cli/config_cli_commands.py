"""
Schema and validate commands for config CLI (file-editing server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core.env_loader import load_dotenv_near_config


def cmd_schema(args: argparse.Namespace) -> int:
    """Database schema apply is not available in file-editing mode."""
    print(
        "Database schema apply is not supported: ai-editor-server uses "
        "code-analysis-server for project metadata.",
        file=sys.stderr,
    )
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration file (JSON structure for file-editing server)."""
    try:
        config_path = Path(args.file)
        if not config_path.exists():
            print(f"Configuration file not found: {config_path}", file=sys.stderr)
            return 1

        load_dotenv_near_config(config_path)
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)

        errors: list[str] = []
        for section in ("server", "ai_editor", "code_analysis_server"):
            if section not in config:
                errors.append(f"Missing required section: {section}")

        ca = config.get("code_analysis_server") or {}
        for key in ("host", "port", "protocol"):
            if key not in ca:
                errors.append(f"code_analysis_server.{key} is required")

        if errors:
            print("Configuration is invalid:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

        print(f"Configuration is valid: {config_path}")
        return 0
    except Exception as exc:
        print(f"Failed to validate configuration: {exc}", file=sys.stderr)
        return 1
