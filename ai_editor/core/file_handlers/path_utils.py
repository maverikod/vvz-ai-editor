"""
Path helpers for universal file handlers (mkdir -p semantics).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def ensure_parent_directories(
    file_path: Path,
    *,
    create_parent_dirs: bool = True,
) -> Optional[str]:
    """
  Ensure the parent directory of ``file_path`` exists.

  When ``create_parent_dirs`` is true, behaves like ``mkdir -p`` on the parent.
  When false, returns an error message if the parent is missing.

  Returns:
      None on success; human-readable error message when parent is required but absent.
  """
    parent = file_path.parent
    if parent == file_path or parent.exists():
        return None
    if create_parent_dirs:
        parent.mkdir(parents=True, exist_ok=True)
        return None
    return f"Parent directory does not exist: {parent}"


def normalize_trailing_newline(text: str) -> str:
    """Ensure file text ends with a single Unix newline."""
    if not text:
        return "\n"
    return text if text.endswith("\n") else text.rstrip("\r\n") + "\n"
