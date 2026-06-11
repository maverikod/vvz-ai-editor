"""Probe module for multi-edit preview diff demos (not a pytest test file)."""


class Widget:
    """Primary widget for preview diff probes."""

    def alpha(self) -> str:
        """Return alpha label."""
        return "alpha"

    def beta(self) -> str:
        """Return beta label."""
        return "beta"

    def gamma(self) -> int:
        """Return gamma count."""
        return 3


def helper(x: int) -> int:
    """Double the input."""
    return x * 2
