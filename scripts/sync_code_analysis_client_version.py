#!/usr/bin/env python3
"""
Copy ``[project].version`` from the repository root ``pyproject.toml`` into
``client/ai_editor_client/version.txt`` (single line, no BOM).

Used so the PyPI package **ai-editor-client** stays aligned with the main
**ai-editor** project version without maintaining two literals.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def read_project_version(pyproject_path: Path) -> str:
    text = pyproject_path.read_text(encoding="utf-8")
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project:
            if stripped.startswith("[") and stripped.endswith("]"):
                break
            if stripped.startswith("version") and "=" in stripped:
                _, _, rhs = stripped.partition("=")
                val = rhs.strip().strip('"').strip("'")
                if not val:
                    continue
                return val
    raise RuntimeError(f"No version = ... found under [project] in {pyproject_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (parent of client/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print version only; do not write version.txt",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    pyproject = root / "pyproject.toml"
    target = root / "client" / "ai_editor_client" / "version.txt"
    ver = read_project_version(pyproject)
    print(f"Root project version: {ver!r}")
    print(f"Target file: {target}")
    if args.dry_run:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ver.strip() + "\n", encoding="utf-8")
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
