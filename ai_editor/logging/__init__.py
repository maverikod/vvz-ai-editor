"""
Unified logging package: format with importance (0-10) for project log output.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ai_editor.logging.unified_logging import (
    LEVEL_TO_IMPORTANCE,
    UNIFIED_DATE_FMT,
    UNIFIED_FORMAT_STR,
    UnifiedFormatter,
    create_unified_formatter,
    importance_from_level,
    install_unified_record_factory,
)

__all__ = [
    "LEVEL_TO_IMPORTANCE",
    "UNIFIED_DATE_FMT",
    "UNIFIED_FORMAT_STR",
    "UnifiedFormatter",
    "create_unified_formatter",
    "importance_from_level",
    "install_unified_record_factory",
]
