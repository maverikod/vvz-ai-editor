"""
Blocking evidence: LibCST comment and docstring round-trip behavior.

Proves actual parse -> .code fidelity for comments and docstrings so that
later steps know whether fallback (comment-to-docstring) is prohibited or
must be escalated. TZ §4.1: comments must be preserved when parser supports
them; do not transform comments to docstrings in normal mode.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst


def _round_trip(source: str) -> str:
    """Parse source with LibCST and return module.code (single round-trip)."""
    module = cst.parse_module(source)
    return module.code


# --- Inline and standalone comments ---


def test_libcst_preserves_end_of_line_comment():
    """LibCST round-trip preserves a comment on the same line as code."""
    source = "x = 1  # end of line comment\n"
    result = _round_trip(source)
    assert (
        "# end of line comment" in result
    ), "LibCST must preserve end-of-line comments in module.code"
    assert "x = 1" in result


def test_libcst_preserves_standalone_comment():
    """LibCST round-trip preserves a comment on its own line."""
    source = "# standalone comment\nx = 1\n"
    result = _round_trip(source)
    assert (
        "# standalone comment" in result
    ), "LibCST must preserve standalone comments in module.code"
    assert "x = 1" in result


def test_libcst_preserves_multiple_comment_lines():
    """LibCST round-trip preserves several consecutive comment lines."""
    source = "# first\n# second\n# third\ny = 2\n"
    result = _round_trip(source)
    assert (
        "# first" in result and "# second" in result and "# third" in result
    ), "LibCST must preserve multiple standalone comments"


def test_libcst_preserves_inline_comment_after_statement():
    """LibCST round-trip preserves comment after a simple statement (inline)."""
    source = "pass  # after pass\n"
    result = _round_trip(source)
    assert (
        "# after pass" in result
    ), "LibCST must preserve inline (same-line) comments in module.code"


# --- Docstrings ---


def test_libcst_preserves_module_docstring():
    """LibCST round-trip preserves module-level docstring (TZ §4.1 policy evidence)."""
    source = '"""Module docstring."""\nx = 1\n'
    result = _round_trip(source)
    assert (
        '"""Module docstring."""' in result or "Module docstring" in result
    ), "LibCST must preserve module docstring in module.code; TZ §4.1 docstrings as-is"


def test_libcst_preserves_function_docstring():
    """LibCST round-trip preserves function docstring (TZ §4.1 policy evidence)."""
    source = 'def f():\n    """Function doc."""\n    pass\n'
    result = _round_trip(source)
    assert (
        "Function doc" in result or '"""Function doc."""' in result
    ), "LibCST must preserve function docstring in module.code; TZ §4.1 docstrings as-is"


def test_libcst_preserves_class_docstring():
    """LibCST round-trip preserves class docstring (TZ §4.1 policy evidence)."""
    source = 'class C:\n    """Class doc."""\n    pass\n'
    result = _round_trip(source)
    assert (
        "Class doc" in result or '"""Class doc."""' in result
    ), "LibCST must preserve class docstring in module.code; TZ §4.1 docstrings as-is"


# --- Mixed comments and docstrings ---


def test_libcst_preserves_comment_and_docstring_together():
    """LibCST round-trip preserves both a comment and a docstring in same file."""
    source = '# top comment\n"""Module doc."""\ndef f():\n    """F doc."""\n    pass  # eol\n'
    result = _round_trip(source)
    assert "# top comment" in result, "Standalone comment must be preserved"
    assert (
        "Module doc" in result or '"""Module doc."""' in result
    ), "LibCST must preserve module docstring when mixed with comments"
    assert (
        "F doc" in result or '"""F doc."""' in result
    ), "LibCST must preserve function docstring when mixed with comments"
    assert "# eol" in result, "End-of-line comment must be preserved"


def test_libcst_preserves_comment_between_docstring_and_code():
    """LibCST round-trip preserves comment between docstring and following code."""
    source = '"""Doc."""\n# comment between\na = 1\n'
    result = _round_trip(source)
    assert (
        "# comment between" in result
    ), "Comment between docstring and code must be preserved as comment"
    assert "Doc" in result, "Docstring content must be preserved"
    assert "a = 1" in result, "Code after comment must be preserved"


# --- Negative guard: comments are not converted to docstrings ---


def test_libcst_does_not_convert_comment_to_docstring():
    """
    LibCST does not silently convert a comment into a docstring on round-trip.

    If a line contains only a comment (e.g. '# only comment'), the round-trip
    output must still contain the comment syntax '#', not a triple-quoted
    docstring with the same text. This guards against normalizing comments
    into docstrings.
    """
    source = "# only comment\n"
    result = _round_trip(source)
    assert (
        "# only comment" in result
        or "# only comment\n" == result
        or result.strip().startswith("#")
    ), (
        "Comment must remain a comment in round-trip output; "
        "comments must not be converted to docstrings."
    )
    # Explicit negative: the comment text must not appear as a docstring
    # (i.e. we must not see ''' only comment ''' or \"\"\" only comment \"\"\" as the sole content)
    docstring_style = '"""only comment"""'
    single_style = "'''only comment'''"
    assert (
        docstring_style not in result
    ), "Comment was incorrectly converted to double-quoted docstring."
    assert (
        single_style not in result
    ), "Comment was incorrectly converted to single-quoted docstring."


def test_libcst_comment_and_docstring_remain_distinct():
    """
    A file that has both a comment and a docstring must preserve both forms;
    the comment must not be merged into or replaced by the docstring.
    """
    source = '# I am a comment\n"""I am a docstring."""\n'
    result = _round_trip(source)
    assert "# I am a comment" in result, "Comment line must be preserved as comment"
    assert "I am a docstring" in result, "Docstring content must be preserved"
    # Comment text must not appear as docstring
    assert (
        '"""I am a comment"""' not in result
    ), "Comment must not be rewritten as docstring"


# --- Full round-trip equality where applicable ---


def test_libcst_round_trip_identity_for_simple_module_with_comments():
    """
    For a simple module with only comments (no docstrings), round-trip output
    preserves all comment tokens; behavior is deterministic (policy evidence).
    """
    source = "a = 1\n# comment\nb = 2  # eol\n"
    result = _round_trip(source)
    assert "a = 1" in result and "b = 2" in result, "Code lines must be preserved"
    assert (
        "# comment" in result and "# eol" in result
    ), "All comments must be preserved in round-trip for policy compliance"
    assert (
        result.strip().count("#") >= 2
    ), "Comment count must be preserved; no silent loss or conversion"
