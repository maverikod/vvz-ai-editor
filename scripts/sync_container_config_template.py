#!/usr/bin/env python3
"""
Copy bundled container config template to config/ for local Docker mounts.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_editor.config_templates import (
    CONTAINER_TEMPLATE_NAME,
    copy_bundled_template,
)  # noqa: E402


def main() -> int:
    dest = copy_bundled_template(ROOT / "config", overwrite=True)
    print(f"Synced {CONTAINER_TEMPLATE_NAME} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
