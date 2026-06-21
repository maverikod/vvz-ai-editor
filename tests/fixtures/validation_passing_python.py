"""Validation-passing Python sample sources for editor tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

SEARCH_MODULE = '''"""Search test module."""

from __future__ import annotations


def foo() -> int:
    """Return one.

    Returns:
        The integer one.
    """
    return 1
'''

CLEAN_CALC_MODULE = '''"""Clean test file for editor validation smoke tests."""

from __future__ import annotations


def calc(x: int) -> int:
    """Return x plus one.

    Args:
        x: Input value.

    Returns:
        x incremented by one.
    """
    return x + 1
'''

GREET_MODULE = '''"""Editor test module."""

from __future__ import annotations


def greet(name: str) -> str:
    """Build a greeting for a person.

    Args:
        name: Person to greet.

    Returns:
        Greeting string.
    """
    return f"hello {name}"
'''

ADD_MODULE = '''"""Second editor Python sample."""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Sum two integers.

    Args:
        a: First summand.
        b: Second summand.

    Returns:
        The sum of ``a`` and ``b``.
    """
    return a + b
'''

MOD_WITH_FOO = '''"""Module under test for insert-by-node_ref."""

from __future__ import annotations


def foo() -> int:
    """Return one.

    Returns:
        The integer one.
    """
    return 1
'''

BAR_INSERT_LINES = [
    "",
    "",
    "def bar() -> int:",
    '    """Return two.',
    "",
    "    Returns:",
    "        The integer two.",
    '    """',
    "    return 2",
]
