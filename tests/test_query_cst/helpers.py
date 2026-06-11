"""
Helpers for query_cst command tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any


def write_py_file(path: Path, content: str) -> None:
    """Create parent dirs and write Python file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def assert_success_result(result: Any) -> None:
    """Assert result is SuccessResult (avoids isinstance with type aliases)."""
    assert (
        type(result).__name__ == "SuccessResult"
    ), f"expected SuccessResult, got {type(result)}"
    assert hasattr(result, "data")


def assert_error_result(result: Any) -> None:
    """Assert result is ErrorResult (avoids isinstance with type aliases)."""
    assert (
        type(result).__name__ == "ErrorResult"
    ), f"expected ErrorResult, got {type(result)}"
