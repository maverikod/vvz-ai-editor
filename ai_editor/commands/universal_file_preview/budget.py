"""
PreviewBudget (C-013) — response size caps for universal_file_preview.

Two caps:
  preview_lines     — max blocks returned when selector is omitted.
  value_preview_len — max length of any inline scalar value or name.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PreviewBudget:
    """
    Resolved size caps for one preview request (C-013, C-023).

    All values are resolved from caller input or from implementation
    defaults before the NavigationProcedure runs.

    Attributes:
        preview_lines: Max blocks returned when selector is omitted.
                       Must be >= 1.
        value_preview_len: Max characters for any inline scalar or name.
                          Must be >= 1.
        full_text_max_lines: When a Python file has fewer lines than this
                             threshold, the Python handler returns the entire
                             file source as a single text block (C-023).
                             Default 200. Value 0 disables the fallback.
        max_chars: Max characters for the post-render preview payload.
                   Applied after rendering, not inside handlers.
        preview_offset: Character offset into the serialized preview for pagination.
    """

    preview_lines: int
    value_preview_len: int
    full_text_max_lines: int = 200
    max_chars: int = 32_000
    preview_offset: int = 0

    def __post_init__(self) -> None:
        """Validate that numeric caps are in allowed ranges."""
        if self.preview_lines < 1:
            raise ValueError(f"preview_lines must be >= 1, got {self.preview_lines}")
        if self.value_preview_len < 1:
            raise ValueError(
                f"value_preview_len must be >= 1, got {self.value_preview_len}"
            )
        if self.full_text_max_lines < 0:
            raise ValueError(
                f"full_text_max_lines must be >= 0, got {self.full_text_max_lines}"
            )
        if self.max_chars < 1:
            raise ValueError(f"max_chars must be >= 1, got {self.max_chars}")
        if self.preview_offset < 0:
            raise ValueError(f"preview_offset must be >= 0, got {self.preview_offset}")
