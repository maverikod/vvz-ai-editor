"""Unit tests for line-ending preservation across an edit (C-012).

Pins the guarantee the canonical export owes the caller: committing an edited
file changes ONLY the lines the caller actually edited. The line-ending style
of a CRLF (or CR, or mixed) source survives the round trip, and a file without
a trailing newline never gains one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_edit.format_group import FORMAT_TEXT
from ai_editor.commands.universal_file_edit.line_ending_policy import (
    dominant_terminator,
    reapply_line_endings,
    split_terminated_lines,
)
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    compare_session_to_origin,
)
from tests.unit.test_write_compare import _mock_session

CRLF_SRC = b"alpha\r\nbeta\r\ngamma\r\n"
LF_SRC = b"alpha\nbeta\ngamma\n"


def test_split_recognizes_only_real_terminators() -> None:
    assert split_terminated_lines(b"a\r\nb\nc\rd") == [
        (b"a", b"\r\n"),
        (b"b", b"\n"),
        (b"c", b"\r"),
        (b"d", b""),
    ]
    assert split_terminated_lines(b"") == []
    assert split_terminated_lines(b"\r\n") == [(b"", b"\r\n")]
    # Form feed and vertical tab are line breaks for str.splitlines but not here.
    assert split_terminated_lines(b"a\x0cb\x0bc") == [(b"a\x0cb\x0bc", b"")]


def test_dominant_terminator_counts_then_first_appearance() -> None:
    assert dominant_terminator(split_terminated_lines(CRLF_SRC)) == b"\r\n"
    assert dominant_terminator(split_terminated_lines(b"a\r\nb\nc\n")) == b"\n"
    # A tie is broken by first appearance, never by dict ordering.
    assert dominant_terminator(split_terminated_lines(b"a\r\nb\n")) == b"\r\n"
    assert dominant_terminator(split_terminated_lines(b"a\nb\r\n")) == b"\n"
    assert dominant_terminator(split_terminated_lines(b"only one line")) == b"\n"


def test_crlf_edit_changes_only_the_edited_line() -> None:
    result = reapply_line_endings(CRLF_SRC, b"alpha\nBETA\ngamma\n")

    assert result == b"alpha\r\nBETA\r\ngamma\r\n"


def test_crlf_untouched_export_is_byte_identical() -> None:
    assert reapply_line_endings(CRLF_SRC, b"alpha\nbeta\ngamma\n") == CRLF_SRC


def test_crlf_insert_gives_the_new_line_the_dominant_style() -> None:
    result = reapply_line_endings(CRLF_SRC, b"alpha\nbeta\ndelta\ngamma\n")

    assert result == b"alpha\r\nbeta\r\ndelta\r\ngamma\r\n"


def test_lone_cr_source_keeps_lone_cr() -> None:
    result = reapply_line_endings(b"alpha\rbeta\rgamma\r", b"alpha\nBETA\ngamma\n")

    assert result == b"alpha\rBETA\rgamma\r"


def test_lf_source_stays_lf() -> None:
    assert (
        reapply_line_endings(LF_SRC, b"alpha\nBETA\ngamma\n") == b"alpha\nBETA\ngamma\n"
    )


def test_no_trailing_newline_is_not_gained_on_an_edit() -> None:
    origin = b"alpha\nbeta\nno trailing newline"

    assert (
        reapply_line_endings(origin, b"ALPHA\nbeta\nno trailing newline")
        == b"ALPHA\nbeta\nno trailing newline"
    )
    # Even when the exporter appended one of its own.
    assert (
        reapply_line_endings(origin, b"ALPHA\nbeta\nno trailing newline\n")
        == b"ALPHA\nbeta\nno trailing newline"
    )


def test_rewriting_the_final_line_honours_the_caller_s_own_terminator() -> None:
    """A terminator inside the caller's replacement text is an edit, not damage."""
    assert reapply_line_endings(b'{"ok": true', b'{"ok": true}\n') == b'{"ok": true}\n'


def test_crlf_without_trailing_newline_keeps_both_properties() -> None:
    origin = b"alpha\r\nbeta\r\nlast"

    result = reapply_line_endings(origin, b"alpha\nBETA\nlast")

    assert result == b"alpha\r\nBETA\r\nlast"


def test_appending_past_an_unterminated_last_line_terminates_it() -> None:
    """The old final line is no longer final, so it takes the house style."""
    origin = b"alpha\r\nbeta\r\nlast"

    result = reapply_line_endings(origin, b"alpha\nbeta\nlast\nadded")

    assert result == b"alpha\r\nbeta\r\nlast\r\nadded"


def test_mixed_endings_keep_untouched_lines_and_give_edits_the_dominant_style() -> None:
    """Documented decision for a mixed file: per-line preservation.

    ``beta`` was edited so it takes the dominant CRLF; ``gamma``'s lone LF was
    never touched by the caller and must not be rewritten.
    """
    origin = b"alpha\r\nbeta\ngamma\r\ndelta\r\n"

    result = reapply_line_endings(origin, b"alpha\nBETA\ngamma\ndelta\n")

    assert result == b"alpha\r\nBETA\r\ngamma\r\ndelta\r\n"


def test_mixed_endings_untouched_export_is_byte_identical() -> None:
    origin = b"alpha\r\nbeta\ngamma\r\n"

    assert reapply_line_endings(origin, b"alpha\nbeta\ngamma\n") == origin


def test_empty_origin_or_export_is_left_alone() -> None:
    assert reapply_line_endings(b"", b"x\n") == b"x\n"
    assert reapply_line_endings(CRLF_SRC, b"") == b""


@pytest.mark.parametrize(
    "origin,export,expected",
    [
        (CRLF_SRC, b"alpha\nBETA\ngamma\n", b"alpha\r\nBETA\r\ngamma\r\n"),
        (CRLF_SRC, b"alpha\nbeta\ngamma\n", CRLF_SRC),
        (
            b"alpha\r\nbeta\r\nno eol",
            b"alpha\nBETA\nno eol",
            b"alpha\r\nBETA\r\nno eol",
        ),
        (LF_SRC, b"alpha\nBETA\ngamma\n", b"alpha\nBETA\ngamma\n"),
    ],
)
def test_export_of_an_edited_session_carries_the_origin_style(
    tmp_path: Path, origin: bytes, export: bytes, expected: bytes
) -> None:
    """The same guarantee, asserted through the real comparison entry point."""
    origin_path = tmp_path / "fixture.txt"
    draft_path = tmp_path / "fixture.txt.draft"
    origin_path.write_bytes(origin)
    # The draft is what universal-newlines text I/O leaves behind: LF only.
    draft_path.write_bytes(export)
    session = _mock_session(
        format_group=FORMAT_TEXT,
        abs_path=origin_path,
        draft_path=draft_path,
    )

    comparison = compare_session_to_origin(session)

    assert comparison.exported_bytes == expected
    assert comparison.origin_bytes == origin
    assert comparison.result == (
        CompareResult.EQUAL if expected == origin else CompareResult.DIFF
    )
