"""
Shared retry policy for database driver and related layers (config field names are canonical).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class RetryPolicy:
    """Retry parameters derived from database driver config (Step 04)."""

    attempts: int = 3
    delay_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    jitter_seconds: float = 0.05

    @staticmethod
    def from_driver_config(config: Mapping[str, Any]) -> RetryPolicy:
        attempts = 3
        delay_seconds = 0.5
        backoff_multiplier = 2.0
        jitter_seconds = 0.05
        if "write_retry_attempts" in config:
            attempts = int(config["write_retry_attempts"])
        if "write_retry_delay_seconds" in config:
            delay_seconds = float(config["write_retry_delay_seconds"])
        if "write_retry_backoff_multiplier" in config:
            backoff_multiplier = float(config["write_retry_backoff_multiplier"])
        if "write_retry_jitter_seconds" in config:
            jitter_seconds = float(config["write_retry_jitter_seconds"])
        return RetryPolicy(
            attempts=attempts,
            delay_seconds=delay_seconds,
            backoff_multiplier=backoff_multiplier,
            jitter_seconds=jitter_seconds,
        )

    def delay_for_attempt(self, attempt_1based: int) -> float:
        """Exponential delay for attempt (1 = first), plus bounded random jitter."""
        if attempt_1based < 1:
            attempt_1based = 1
        base = self.delay_seconds * (self.backoff_multiplier ** (attempt_1based - 1))
        jitter = random.uniform(
            -self.jitter_seconds,
            self.jitter_seconds,
        )
        return max(0.0, base + jitter)
