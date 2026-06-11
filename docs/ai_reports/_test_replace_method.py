"""Temporary test file for cst_modify_tree class method replace fix.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com"""
from __future__ import annotations


class Counter:
    """Simple counter class for testing CST replace.

    Attributes:
        _value: Current counter value.
        _step: Increment step.
    """

    def __init__(self, start: int = 0, step: int = 1) -> None:
        """Initialise counter.

        Args:
            start: Initial value.
            step: Increment step.
        """
        self._value = start
        self._step = step

    def increment(self) -> int:
        """Increment counter by step and return new value.

        Returns:
            New counter value.
        """
        self._value += self._step
        return self._value

    def reset(self) -> None:
        """Reset counter to zero.

        Returns:
            None.
        """
        self._value = 0

    def value(self) -> int:
        """Return current counter value.

        Returns:
            Current value.
        """
        return self._value