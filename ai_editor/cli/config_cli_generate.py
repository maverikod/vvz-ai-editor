"""
Generate command for config CLI (file-editing server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import sys


def cmd_generate(args: argparse.Namespace) -> int:
    """Config generation is not bundled; copy config.json and edit manually."""
    out = getattr(args, "out", None) or "config.json"
    print(
        "Automatic config generation was removed with database/worker features.\n"
        f"Copy config.json to {out} and adjust server / code_analysis_server sections.",
        file=sys.stderr,
    )
    return 1
