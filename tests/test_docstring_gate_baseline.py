"""Regression tests for docstring-gate baseline scoping (bug 2f817afc).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.file_validation.handler_validators import (
    _validate_python_handler,
)

LEGACY = (
    '"""Module docstring."""\n'
    "\n"
    "\n"
    "def alpha():\n"
    "    return 1\n"
    "\n"
    "\n"
    "def beta() -> int:\n"
    '    """Return two.\n'
    "\n"
    "    Returns:\n"
    "        Fixed number.\n"
    '    """\n'
    "    return 2\n"
)

EDITED = LEGACY.replace("return 2", "return 22")

BROKEN_EDIT = EDITED.replace(
    'def beta() -> int:\n    """Return two.\n\n    Returns:\n'
    '        Fixed number.\n    """\n',
    "def beta() -> int:\n",
)


def test_preexisting_violations_are_grandfathered(tmp_path: Path) -> None:
    """Editing one entity must not fail on legacy findings elsewhere."""
    results = _validate_python_handler(
        EDITED,
        tmp_path / "legacy.py",
        docstring_baseline=LEGACY,
    )
    assert results["docstrings"].success, results["docstrings"].errors


def test_new_violations_still_fail(tmp_path: Path) -> None:
    """Removing a docstring the baseline had must still block the commit."""
    results = _validate_python_handler(
        BROKEN_EDIT,
        tmp_path / "legacy.py",
        docstring_baseline=LEGACY,
    )
    assert not results["docstrings"].success
    joined = "\n".join(results["docstrings"].errors)
    assert "beta" in joined
    assert "alpha" not in joined


def test_no_baseline_keeps_full_enforcement(tmp_path: Path) -> None:
    """Without a baseline the whole-file policy applies unchanged."""
    results = _validate_python_handler(EDITED, tmp_path / "legacy.py")
    assert not results["docstrings"].success
