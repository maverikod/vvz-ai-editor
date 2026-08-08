#!/usr/bin/env python3
"""
Verify that the server, the client and the engine all carry the SAME version.

This script used to COPY ``[project].version`` from the root ``pyproject.toml``
into ``client/ai_editor_client/version.txt``. That copy had to be remembered,
and it was not: the two numbers were measured ten releases apart (1.0.93 against
1.0.83) before the packaging change that removed the need for it.

There is nothing left to copy. The repository root ``VERSION`` file is the one
source of truth; all three ``pyproject.toml`` files read it through
``[tool.setuptools.dynamic]``, and the two outside the root reach it through
symlinks (``src/VERSION`` and ``client/ai_editor_client/version.txt``), because
setuptools refuses to read a version file outside a distribution's own root.
sdist and wheel builds copy the resolved CONTENT, so a published artifact never
carries a dangling link.

So this command now VERIFIES instead of writing, and exits non-zero on drift.
The same invariant is asserted by ``tests/unit/test_version_pinning.py``; this
script exists so a release operator can check it without running pytest.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

VERSION_FILENAME = "VERSION"


def read_declared_version(root: Path) -> str:
    """The one number, from the one file."""
    version_file = root / VERSION_FILENAME
    if not version_file.is_file():
        raise RuntimeError(f"missing single source of truth: {version_file}")
    return version_file.read_text(encoding="utf-8").strip()


def _report(label: str, path: Path, expected: str) -> bool:
    if not path.is_file():
        print(f"  {label:<38} MISSING  ({path})")
        return False
    actual = path.read_text(encoding="utf-8").strip()
    link = f" -> {path.readlink()}" if path.is_symlink() else "  (not a symlink)"
    ok = actual == expected
    print(f"  {label:<38} {actual:<10} {'OK' if ok else 'DRIFT'}{link}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (parent of client/ and src/)",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()

    declared = read_declared_version(root)
    print(f"Declared version ({root / VERSION_FILENAME}): {declared}")
    print("Version sources:")
    results = [
        _report("ai-editor (server)", root / VERSION_FILENAME, declared),
        _report(
            "ai-editor-tree-engine (engine)",
            root / "src" / VERSION_FILENAME,
            declared,
        ),
        _report(
            "ai-editor-client (client)",
            root / "client" / "ai_editor_client" / "version.txt",
            declared,
        ),
    ]
    if not all(results):
        print(
            "\nDRIFT: the server, the client and the engine must carry the same "
            "version. Restore the symlinks into the root VERSION file:\n"
            "  ln -sfn ../VERSION src/VERSION\n"
            "  ln -sfn ../../VERSION client/ai_editor_client/version.txt",
            file=sys.stderr,
        )
        return 1
    print("\nAll three distributions carry the same version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
