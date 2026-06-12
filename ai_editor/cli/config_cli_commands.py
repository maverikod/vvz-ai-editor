"""
Schema and validate commands for config CLI (file-editing server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_editor.core.config_validation import validate_config_file


def cmd_schema(args: argparse.Namespace) -> int:
    """Database schema apply is not available in file-editing mode."""
    print(
        "Database schema apply is not supported: ai-editor-server uses "
        "code-analysis-server for project metadata.",
        file=sys.stderr,
    )
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration (adapter SimpleConfigValidator + editor extensions)."""
    try:
        config_path = Path(args.file)
        if not config_path.exists():
            print(f"Configuration file not found: {config_path}", file=sys.stderr)
            return 1
        return validate_config_file(config_path.resolve())
    except Exception as exc:
        print(f"Failed to validate configuration: {exc}", file=sys.stderr)
        return 1
