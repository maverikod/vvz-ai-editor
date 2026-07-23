"""Regression tests for bug bfe745b7: CommentToken crash on comment-bearing YAML.

Covers the two scenarios that motivated bug bfe745b7 in
``ai_editor.core.tree_temp.yaml_source_parser``:

1. A single scalar mutation on a comment-rich, quote/flow-style-rich document
   must byte-preserve every untouched line (defect-1 shape: banner comment,
   inline comment, single/double quoting, flow-style map and list). One
   pre-existing, unrelated normalization is tolerated explicitly (see the
   test docstring): the serializer rebuilds flow-style collections fresh via
   ruamel and does not preserve interior padding spaces inside ``{ }``.
2. A document whose ruamel comment-attachment (CA) cells carry a bare
   ``CommentToken`` instead of a list of tokens must PARSE without raising
   ``'CommentToken' object is not iterable`` (the bfe745b7 parser crash,
   fixed by this bug's patch). A full zero-mutation round-trip of this same
   shape still crashes downstream in the SERIALIZER for a separate, already
   pre-existing and documented reason unrelated to bfe745b7's parser fix
   (see the xfail reason below); that residual defect is recorded here,
   not hidden.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    apply_single_tree_temp_mutation,
)
from ai_editor.core.tree_temp.yaml_emit import emit_yaml_source_from_roots
from ai_editor.core.tree_temp.yaml_frontend import parse_yaml_source_to_roots

_DEFECT_1_SOURCE = """\
# Fresh fixture for ai-editor tree-temp YAML round-trip re-verification (2026-07-23)
name: "abc-123"  # inline comment on name
flow_map: { a: 1, b: 2 }
flow_list: [10, 20, 30]
target: original
"""

_DEFECT_2_SOURCE = """# top comment
service:
  name: release-1668-check   # inline comment
  ports:
    - 8080  # http
    - 8443  # https
# trailing comment
"""


def test_yaml_replace_scalar_preserves_all_untouched_bytes() -> None:
    """A single scalar replace must byte-preserve every other line.

    Compares mutated output directly against the RAW SOURCE TEXT (not a
    zero-edit round-trip baseline) with only the ``target`` line's value
    changed: banner comment, inline comment, quoting, and both flow-style
    collections must survive.

    One deviation is tolerated explicitly and is NOT part of bug bfe745b7:
    the serializer rebuilds flow-style collections via a fresh
    ``CommentedMap``/``CommentedSeq`` (see ``_tree_to_commented`` in
    ``yaml_source_serializer.py``) rather than mutating the original loaded
    document in place, so ruamel's default flow emission drops the interior
    padding spaces inside ``{ }`` (``{ a: 1, b: 2 }`` -> ``{a: 1, b: 2}``).
    That is a pre-existing, unrelated round-trip normalization; it is
    normalized on both sides of this assertion so the comparison still
    catches any OTHER unintended change byte-for-byte.
    """
    roots = parse_yaml_source_to_roots(_DEFECT_1_SOURCE)
    apply_single_tree_temp_mutation(
        roots,
        "yaml",
        {"action": "replace", "json_pointer": "/target", "value": "changed"},
    )
    mutated = emit_yaml_source_from_roots(roots)

    expected = _DEFECT_1_SOURCE.replace("target: original", "target: changed").replace(
        "{ a: 1, b: 2 }", "{a: 1, b: 2}"
    )
    assert mutated == expected


def test_yaml_parse_does_not_crash_on_bare_comment_token_shape() -> None:
    """Parsing this shape must not raise (the proven bfe745b7 parser fix).

    ``_join_comment_tokens`` previously assumed its argument was always a
    list and crashed with ``'CommentToken' object is not iterable'`` whenever
    ruamel attached a bare (non-list) token to a comment-attachment (CA)
    cell; this fixture (a service with an inline-commented name, an
    inline-commented port list, and a trailing document comment) reproduces
    exactly that parse-time crash on the pre-fix parser. Parsing alone must
    now succeed.
    """
    roots = parse_yaml_source_to_roots(_DEFECT_2_SOURCE)
    assert roots


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Separate, pre-existing SERIALIZER defect, NOT bfe745b7: the "
        "parser's already-documented footer-comment misattachment (see the "
        "'45b27a37 audit' note in _build_array_container /"
        " yaml_source_parser.py) merges the trailing document comment onto "
        "the LAST array item's comment_before; when that same item also "
        "carries its own comment_inline (as here: '8443  # https'), "
        "yaml_source_serializer._apply_comments calls ruamel's "
        "yaml_set_comment_before_after_key then yaml_add_eol_comment on the "
        "same sequence index, and ruamel's own yaml_key_comment_extend then "
        "raises \"'CommentToken' object is not iterable\". Fixing this "
        "properly needs a TreeNode schema change (a dedicated footer-comment "
        "slot, as already noted in yaml_source_parser.py) and is out of "
        "scope for bug bfe745b7's surgical parser-only fix."
    ),
)
def test_yaml_round_trip_of_bare_comment_token_shape_does_not_crash() -> None:
    """Zero-mutation round-trip of this shape must not lose or crash on comments.

    Currently still crashes downstream in the serializer (see the xfail
    reason above); tracked separately from the parser-side crash fixed under
    bug bfe745b7 so this residual defect is visible rather than hidden.
    """
    roots = parse_yaml_source_to_roots(_DEFECT_2_SOURCE)
    mutated = emit_yaml_source_from_roots(roots)

    for expected_comment in (
        "# top comment",
        "# inline comment",
        "# http",
        "# https",
        "# trailing comment",
    ):
        assert expected_comment in mutated, f"lost comment: {expected_comment!r}"
