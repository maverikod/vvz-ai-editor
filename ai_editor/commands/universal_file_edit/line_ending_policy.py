"""
Line-ending and trailing-newline preservation for the canonical export (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The whole editing pipeline reads source through universal-newlines text I/O:
``Path.read_text``, libcst and ruamel all decode ``\\r\\n`` and a lone ``\\r``
to ``\\n``, and every draft is written back as LF. The line-ending STYLE of the
file the caller opened therefore never survives into the canonical export, and
committing an edited CRLF file used to rewrite every line ending on disk --
byte damage nobody asked for.

This module puts the style back. It takes the pristine Origin Snapshot bytes and
the LF-only canonical export and re-renders the export in the origin's own
terminators, so a commit changes only the lines the caller actually edited.

Two rules, both content-derived and both deliberate:

* **Per-line preservation, not file-wide normalization.** Export lines are
  aligned to origin lines with :class:`difflib.SequenceMatcher` over the line
  CONTENT (terminators stripped). A line that survived the edit unchanged is
  re-terminated with the byte sequence it had in the origin; a line the caller
  inserted or rewrote gets the file's DOMINANT terminator. For a uniform CRLF
  file the two rules coincide, so the whole file stays CRLF. For a file with
  MIXED endings this is the only reading of "preserve" that does not invent a
  change: normalizing a mixed file to one style would rewrite lines the caller
  never touched, and picking per-line would leave a new line with no defensible
  terminator, so untouched lines keep their own bytes and new lines follow the
  house style. The dominant terminator is the most frequent one, ties broken by
  first appearance, so it is stable and never depends on dict ordering.

* **A file never gains a trailing newline behind the caller's back.** When the
  origin's last line had no terminator and that same line comes out of the edit
  UNTOUCHED, it keeps none: neither an edit elsewhere in the file nor the
  sidecar exporter's own ``normalize_trailing_newline`` may append one. When the
  caller rewrote or replaced the final line, the terminator in their own
  replacement text is an edit like any other and is honored.

Together these make the identity case exact: when the export equals the origin's
LF-normalized form, the result is the origin byte for byte.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import List, Tuple

LF = b"\n"
CRLF = b"\r\n"
CR = b"\r"

#: One source line: its content without a terminator, plus the terminator bytes
#: that followed it (empty for a final line that ends the file without one).
TerminatedLine = Tuple[bytes, bytes]


def split_terminated_lines(raw: bytes) -> List[TerminatedLine]:
    """Split ``raw`` into lines, keeping each line's own terminator separate.

    Only the three real line terminators are recognized -- ``\\r\\n``, ``\\n``
    and a lone ``\\r`` -- deliberately narrower than ``str.splitlines``, which
    also breaks on form feed, vertical tab and the Unicode separators and would
    silently invent line boundaries inside file content.

    Args:
        raw: Raw file bytes.

    Returns:
        ``[(content, terminator), ...]`` in file order. Empty for empty input.
        The last entry carries an empty terminator when the file does not end
        with a line break; there is never a trailing empty-content entry.
    """
    lines: List[TerminatedLine] = []
    start = index = 0
    size = len(raw)
    while index < size:
        current = raw[index : index + 1]
        if current == CR:
            terminator = CRLF if raw[index + 1 : index + 2] == LF else CR
        elif current == LF:
            terminator = LF
        else:
            index += 1
            continue
        lines.append((raw[start:index], terminator))
        index += len(terminator)
        start = index
    if start < size:
        lines.append((raw[start:], b""))
    return lines


def dominant_terminator(lines: List[TerminatedLine]) -> bytes:
    """Return the file's house line terminator: the most frequent one.

    Ties are broken by first appearance in the file, so the answer is stable and
    independent of iteration order. A file with no line break at all has no
    evidence for any style and reports ``\\n``.

    Args:
        lines: Output of :func:`split_terminated_lines`.

    Returns:
        ``b"\\r\\n"``, ``b"\\n"`` or ``b"\\r"``.
    """
    counts: dict[bytes, int] = {}
    order: List[bytes] = []
    for _content, terminator in lines:
        if not terminator:
            continue
        if terminator not in counts:
            counts[terminator] = 0
            order.append(terminator)
        counts[terminator] += 1
    if not order:
        return LF
    best = order[0]
    for terminator in order[1:]:
        if counts[terminator] > counts[best]:
            best = terminator
    return best


def reapply_line_endings(origin: bytes, exported: bytes) -> bytes:
    """Re-render the LF-only canonical export in the origin's line-ending style.

    See the module docstring for the two rules this implements. The function is
    a pure content transformation: it never consults a mutation flag, so it can
    neither lose an edit nor fake one -- only the terminator bytes of the export
    are touched, never its line content.

    Args:
        origin: Pristine Origin Snapshot bytes, in whatever style the file had.
        exported: Canonical export produced by the format-specific serializer,
            LF-only because of universal-newlines decoding upstream.

    Returns:
        ``exported`` with every line terminated the way the origin terminated
        it, and with no trailing newline the origin did not have. Returned
        unchanged when either side is empty -- an empty origin carries no style
        to preserve (a ``create=true`` draft opened from ``""``).
    """
    origin_lines = split_terminated_lines(origin)
    export_lines = split_terminated_lines(exported)
    if not origin_lines or not export_lines:
        return exported
    origin_terminators = [terminator for _content, terminator in origin_lines]
    final_export_terminator = export_lines[-1][1]
    if CR not in origin and (origin_terminators[-1] or not final_export_terminator):
        # Pure-LF origin whose trailing-newline convention the export already
        # matches: nothing to re-apply, so skip the alignment on by far the most
        # common input.
        return exported
    dominant = dominant_terminator(origin_lines)
    terminators = [dominant] * len(export_lines)
    final_line_untouched = False
    matcher = SequenceMatcher(
        None,
        [content for content, _terminator in origin_lines],
        [content for content, _terminator in export_lines],
        autojunk=False,
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(j2 - j1):
            # An origin line that ended the file carries no terminator; once it
            # is no longer last it must take the house style rather than none.
            carried = origin_terminators[i1 + offset]
            terminators[j1 + offset] = carried or dominant
        if i2 == len(origin_lines) and j2 == len(export_lines):
            final_line_untouched = True
    if not final_export_terminator or (
        final_line_untouched and not origin_terminators[-1]
    ):
        # The file must not GAIN a trailing newline: an origin whose last line
        # had none keeps none, as long as that last line is the caller's own
        # untouched text. When the caller rewrote or replaced the final line,
        # the terminator they wrote is an edit and is honored.
        terminators[-1] = b""
    return b"".join(
        content + terminator
        for (content, _original), terminator in zip(export_lines, terminators)
    )
