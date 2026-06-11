"""
Unified logging format with importance (0-10) for all project log output.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

# Default importance (0-10) per standard level when not set explicitly (see LOG_IMPORTANCE_CRITERIA.md)
LEVEL_TO_IMPORTANCE = {
    "DEBUG": 2,
    "INFO": 4,
    "WARNING": 6,
    "ERROR": 8,
    "CRITICAL": 10,
}

UNIFIED_DATE_FMT = "%Y-%m-%d %H:%M:%S"
UNIFIED_FORMAT_STR = "%(asctime)s | %(levelname)-8s | %(importance)s | %(message)s"


def importance_from_level(level_name: str) -> int:
    """Return importance 0-10 for a standard log level name. Returns 4 for unknown."""
    return LEVEL_TO_IMPORTANCE.get((level_name or "").strip().upper(), 4)


def _set_importance_if_missing(record: logging.LogRecord) -> None:
    """Set record.importance from level if not already set (by extra or factory)."""
    if getattr(record, "importance", None) is None:
        record.importance = importance_from_level(record.levelname)


def install_unified_record_factory() -> None:
    """
    Chain the LogRecord factory so callers can keep installing hooks.

    Do not set ``importance`` here: ``Logger.makeRecord`` merges ``extra`` after
    the factory runs; pre-setting ``record.importance`` would make
    ``logger.info(..., extra={"importance": N})`` raise KeyError. Importance is
    filled by :class:`UnifiedFormatter` via :func:`_set_importance_if_missing`,
    or supplied via ``extra`` on the logging call.
    """
    old_factory = logging.getLogRecordFactory()

    def _factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        return old_factory(*args, **kwargs)

    logging.setLogRecordFactory(_factory)


class UnifiedFormatter(logging.Formatter):
    """
    Formatter that outputs: timestamp | level | importance | message.
    Importance is taken from record.importance (set by extra or by record factory).
    Fallback: sets importance from level when factory was not installed.
    """

    def format(self, record: logging.LogRecord) -> str:
        _set_importance_if_missing(record)
        return super().format(record)


def create_unified_formatter(
    fmt: str = UNIFIED_FORMAT_STR,
    datefmt: str = UNIFIED_DATE_FMT,
) -> UnifiedFormatter:
    """Create a UnifiedFormatter with project default format and date format."""
    return UnifiedFormatter(fmt=fmt, datefmt=datefmt)
