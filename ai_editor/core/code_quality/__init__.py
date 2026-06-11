"""
Code quality tools module.

Provides programmatic access to black, flake8, and mypy as libraries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .formatter import format_code_with_black
from .linter import lint_with_flake8
from .type_checker import type_check_with_mypy

__all__ = [
    "format_code_with_black",
    "lint_with_flake8",
    "type_check_with_mypy",
]
