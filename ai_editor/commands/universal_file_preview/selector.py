"""
Selector (C-007) — three-form block-set picker for universal_file_preview.

Form A: slice string (contains ':' or starts with '-').
Form B: list[int] — explicit zero-based block indices.
Form C: list[str] — explicit block node identifiers.
When selector is omitted, returns first preview_lines blocks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .errors import (
    INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY,
    INPUT_ERROR_INVALID_SELECTOR_FORM,
    INPUT_ERROR_MIXED_SELECTOR_LIST,
    INPUT_ERROR_OUT_OF_RANGE_INDEX,
    INPUT_ERROR_SELECTOR_ON_EMPTY,
    INPUT_ERROR_UNKNOWN_IDENTIFIER,
    PreviewError,
    input_error,
)
from .models import Node


def apply_selector(
    raw: str | list | None,
    block_set: list[Node],
    preview_lines: int,
) -> list[Node] | PreviewError:
    """
    Apply the Selector to a block set and return the selected subset.

    Dispatches on the runtime type and shape of raw:
      None        → first preview_lines blocks (natural order)
      str         → Form A slice (must contain ':' or start with '-')
      list[int]   → Form B explicit index list (natural order NOT preserved;
                     order follows caller-given sequence)
      list[str]   → Form C explicit identifier list (caller-given order)

    Args:
        raw: Selector value from the caller, or None.
        block_set: Complete ordered block set of the focus node.
        preview_lines: Cap used when raw is None.

    Returns:
        Ordered list of selected Node objects, or PreviewError.
    """
    if raw is None:
        return block_set[:preview_lines]

    if isinstance(raw, str):
        if ":" not in raw and not raw.startswith("-"):
            return input_error(
                INPUT_ERROR_INVALID_SELECTOR_FORM,
                "Slice selector must contain ':' or start with '-'.",
            )
        indices = _parse_slice(raw, len(block_set))
        return [block_set[i] for i in indices]

    if isinstance(raw, list) and raw:
        if not (
            all(isinstance(x, int) for x in raw) or all(isinstance(x, str) for x in raw)
        ):
            return input_error(
                INPUT_ERROR_MIXED_SELECTOR_LIST,
                "Selector list must be all ints or all str, not mixed.",
            )
        if len(raw) != len(set(raw)):
            return input_error(
                INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY,
                "Duplicate entries in selector list.",
            )
        if not block_set:
            return input_error(
                INPUT_ERROR_SELECTOR_ON_EMPTY,
                "Selector list requires a non-empty block set.",
            )
        first = raw[0]
        if isinstance(first, int):
            for idx in raw:
                if idx < 0 or idx >= len(block_set):
                    return input_error(
                        INPUT_ERROR_OUT_OF_RANGE_INDEX,
                        f"Index {idx} out of range [0, {len(block_set)}).",
                    )
            return [block_set[i] for i in raw]
        ref_map = {n.node_ref: n for n in block_set}
        result: list[Node] = []
        for ident in raw:
            node = ref_map.get(ident)
            if node is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_IDENTIFIER,
                    f"Identifier {ident!r} not found in block set.",
                )
            result.append(node)
        return result

    return block_set[:preview_lines]


def _parse_slice(raw: str, length: int) -> list[int]:
    """Parse a Python-style slice string into an index range."""
    parts = raw.split(":", 2)
    while len(parts) < 3:
        parts.append("")
    start_s, stop_s, step_s = parts[0], parts[1], parts[2]

    def _parse_optional_int(s: str) -> int | None:
        s = s.strip()
        if s == "":
            return None
        return int(s)

    start = _parse_optional_int(start_s)
    stop = _parse_optional_int(stop_s)
    step_val = _parse_optional_int(step_s)
    if step_val is None:
        step_val = 1

    normalized = slice(start, stop, step_val).indices(length)
    return list(range(*normalized))
