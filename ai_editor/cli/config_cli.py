"""
CLI interface for configuration generator and validator.

Based on mcp-proxy-adapter CLI with ai_editor specific extensions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
from typing import Optional

from .config_cli_commands import cmd_schema, cmd_validate
from .config_cli_generate import cmd_generate
from .config_cli_parser import build_parser


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Optional command line arguments (for testing).

    Returns:
        Exit code.
    """
    parser = build_parser(cmd_generate, cmd_validate, cmd_schema)
    args = parser.parse_args(argv)

    if hasattr(args, "queue_enabled") and hasattr(args, "queue_disabled"):
        if args.queue_disabled:
            args.queue_enabled = False
        elif args.queue_enabled:
            args.queue_enabled = True
        else:
            args.queue_enabled = True
    if hasattr(args, "queue_in_memory") and hasattr(args, "queue_persistent"):
        if args.queue_persistent:
            args.queue_in_memory = False
        elif args.queue_in_memory:
            args.queue_in_memory = True
        else:
            args.queue_in_memory = True

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
