"""
Line range validation and bracket-syntax parsing for universal text operations.

All line numbers are **1-based** and **inclusive** on both ends (``start_line`` and
``end_line``), matching MCP text-command conventions.

Read paths may **clamp** out-of-range bounds to the file; replace / save / delete
paths must use **strict** validation (see ``validate_range_against_length``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class LineRange:
    """Closed line interval [start_line, end_line], both 1-based inclusive."""

    start_line: int
    end_line: int


def _strip_brackets(spec: str) -> str:
    s = spec.strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise ValueError(f"Range must be bracketed, e.g. [12,15]: {spec!r}")
    return s[1:-1].strip()


def _reject_non_positive(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be >= 1 (1-based); got {value}")


def _parse_inner(inner: str) -> Tuple[Union[int, str], Union[int, str]]:
    """
    Parse bracket interior after optional whitespace.

    Returns (left, right) where each side is int or literal ``"open"`` for an
    open bound (colon with nothing on that side).
    """
    inner = inner.strip()
    if not inner:
        raise ValueError("empty range inside brackets")

    if "," in inner and ":" in inner:
        raise ValueError("invalid range: cannot mix ',' and ':'")

    if "," in inner:
        left_s, right_s = inner.split(",", 1)
        left_s, right_s = left_s.strip(), right_s.strip()
        if not left_s or not right_s:
            raise ValueError("invalid closed range: missing operand")
        try:
            return (int(left_s), int(right_s))
        except ValueError as e:
            raise ValueError(f"invalid integer in range: {inner!r}") from e

    if ":" in inner:
        left_s, right_s = inner.split(":", 1)
        left_s, right_s = left_s.strip(), right_s.strip()
        if left_s == "" and right_s == "":
            raise ValueError("invalid range [:]")
        if left_s != "" and right_s != "":
            raise ValueError(
                "use comma for closed range, e.g. [12,15], not a colon",
            )
        left: Union[int, str]
        right: Union[int, str]
        if left_s == "":
            left = "open"
        else:
            try:
                left = int(left_s)
            except ValueError as e:
                raise ValueError(f"invalid integer in range: {inner!r}") from e
        if right_s == "":
            right = "open"
        else:
            try:
                right = int(right_s)
            except ValueError as e:
                raise ValueError(f"invalid integer in range: {inner!r}") from e
        return (left, right)

    try:
        n = int(inner)
        return (n, n)
    except ValueError as e:
        raise ValueError(f"invalid range: {inner!r}") from e


def parse_bracket_range(spec: str, *, total_lines: Optional[int] = None) -> LineRange:
    """
    Parse text range syntax: ``[12]``, ``[12,15]``, ``[:12]``, ``[11:]``.

    - ``[n]`` → single line ``n``.
    - ``[a,b]`` → inclusive closed interval (``a``..``b``).
    - ``[:b]`` → from line ``1`` through ``b`` inclusive (open start).
    - ``[a:]`` → from line ``a`` through end of file (**requires** ``total_lines``).

    Negative indices are rejected. After resolution, ``start_line <= end_line`` is
    required; otherwise :exc:`ValueError`.

    ``total_lines`` is the number of logical lines in the file (``len(splitlines)``).
    It is required for ``[a:]`` and recommended for validating open-end ranges on
    empty files.
    """
    inner = _strip_brackets(spec)
    left, right = _parse_inner(inner)

    if isinstance(left, int) and isinstance(right, int):
        _reject_non_positive("start_line", left)
        _reject_non_positive("end_line", right)
        if left > right:
            raise ValueError("start_line must be <= end_line")
        return LineRange(left, right)

    if left == "open" and isinstance(right, int):
        _reject_non_positive("end_line", right)
        resolved = LineRange(1, right)
        if resolved.start_line > resolved.end_line:
            raise ValueError("start_line must be <= end_line")
        return resolved

    if isinstance(left, int) and right == "open":
        _reject_non_positive("start_line", left)
        if total_lines is None:
            raise ValueError("total_lines is required for open-end range [n:]")
        if total_lines < 1:
            raise ValueError(
                "open-end range [n:] is invalid for an empty file (0 lines)"
            )
        resolved = LineRange(left, total_lines)
        if resolved.start_line > resolved.end_line:
            raise ValueError("start_line must be <= end_line")
        return resolved

    raise ValueError(f"unsupported bracket range: {spec!r}")


def parse_bracket_ranges(
    specs: Sequence[str],
    *,
    total_lines: Optional[int] = None,
) -> List[LineRange]:
    """
    Parse multiple bracket specs and ensure **pairwise non-overlapping** intervals.

    Touching ranges that share a line (e.g. ``[1,2]`` and ``[2,3]``) count as
    overlapping and are rejected.
    """
    ranges = [parse_bracket_range(s, total_lines=total_lines) for s in specs]
    validate_non_overlapping(ranges)
    return ranges


def validate_inclusive_range(
    start_line: int,
    end_line: int,
    *,
    strict_positive: bool = True,
) -> None:
    """Raise ValueError with human-readable message if invalid."""
    if strict_positive:
        if start_line < 1 or end_line < 1:
            raise ValueError("Line numbers must be >= 1")
    if start_line > end_line:
        raise ValueError("start_line must be <= end_line")


def validate_range_against_length(
    start_line: int,
    end_line: int,
    total_lines: int,
    *,
    strict: bool,
) -> None:
    """
    For writes/replace/delete: ``strict=True`` rejects out-of-range (INVALID_RANGE).

    For reads: ``strict=False`` allows clamping by caller (see ``clamp_read_range``).
    """
    validate_inclusive_range(start_line, end_line)
    if strict:
        if total_lines == 0:
            raise ValueError("empty file")
        if start_line > total_lines or end_line > total_lines:
            raise ValueError(
                f"Range [{start_line},{end_line}] out of file bounds ({total_lines} lines)",
            )


def clamp_read_range(
    start_line: int,
    end_line: int,
    total_lines: int,
) -> Tuple[int, int]:
    """Clamp 1-based inclusive range to existing lines (read compatibility)."""
    if total_lines <= 0:
        return (1, 0)
    validate_inclusive_range(start_line, end_line)
    low = max(1, min(start_line, total_lines))
    high = max(1, min(end_line, total_lines))
    if low > high:
        low, high = high, low
    return (low, high)


def ranges_overlap(a: LineRange, b: LineRange) -> bool:
    """True if closed intervals overlap."""
    return not (a.end_line < b.start_line or b.end_line < a.start_line)


def validate_non_overlapping(ranges: Sequence[LineRange]) -> None:
    """Raise ValueError if any pair overlaps."""
    rs = sorted(ranges, key=lambda r: (r.start_line, r.end_line))
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            if ranges_overlap(rs[i], rs[j]):
                raise ValueError(
                    f"Overlapping ranges: [{rs[i].start_line},{rs[i].end_line}] "
                    f"and [{rs[j].start_line},{rs[j].end_line}]",
                )


def merge_adjacent_ranges_for_replace(
    lines: List[str],
    replacements: Sequence[Tuple[LineRange, List[str]]],
) -> List[str]:
    """
    Apply replacements bottom-to-top so indices stay stable.

    ``replacements``: (range, new_lines) each range inclusive 1-based.
    """
    validate_non_overlapping([r for r, _ in replacements])
    work = lines[:]
    ordered = sorted(
        replacements,
        key=lambda x: (x[0].start_line, x[0].end_line),
        reverse=True,
    )
    for lr, new_lines in ordered:
        validate_range_against_length(
            lr.start_line,
            lr.end_line,
            len(work),
            strict=True,
        )
        lo = lr.start_line - 1
        hi = lr.end_line - 1
        work = work[:lo] + list(new_lines) + work[hi + 1 :]
    return work
