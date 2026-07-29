"""Regression tests for bug 20b4ba84 residual: silent YAML comment corruption.

Bug 20b4ba84's original ``'CommentToken' object is not iterable`` parser
crash was fixed by commit 3762ea0 (see
``tests/test_tree_temp_yaml_comment_token_crash_regression.py``). What
remained -- observed live on 1.0.78 pipeline-check evidence -- is silent
comment corruption after an unrelated minimal scalar edit + commit on a
document shaped like the fixture below:

1. The inline comment on a mapping entry (``name``) was lost entirely.
2. The trailing document-level comment was mis-attached into the *middle*
   of a sibling sequence (between its last two items) instead of landing
   after the sequence's last item / at document end.

Root mechanisms (fixed alongside these tests):

- Symptom 2 (footer mis-attachment): ``yaml_source_parser._build_object`` /
  ``_build_array_container`` / ``_document_roots`` folded a trailing
  "pending" comment (whatever followed the last child, with nothing else
  after it in the source) onto that last child's ``comment_before`` --
  which the serializer renders *before* the child, not after. Fixed by
  ``_attach_trailing_footer`` (yaml_source_parser.py), which instead
  appends the footer as a raw continuation line on the child's own
  ``comment_inline`` slot -- mirroring the exact raw shape ruamel itself
  produces when it folds a trailing comment onto the last token in the
  document (verified: ``ca.end``/``yaml_end_comment_extend`` and per-key
  ``after=`` comments are both inert on a freshly-built ruamel document in
  this ruamel version, so neither can carry the footer). The serializer's
  ``_apply_seq_inline_comment`` / ``_apply_map_inline_comment`` /
  ``_set_inline_comment_cell`` (yaml_source_serializer.py) re-emit that raw
  shape directly, bypassing ``yaml_add_eol_comment``'s automatic ``"# "``
  prefix which would otherwise corrupt a leading blank line.

- Symptom 1 (inline-comment loss on a plain scalar replace): the tree
  mutation path's ``_merge_payload_keep_identity``
  (``ai_editor/commands/universal_file_edit/tree_temp_edit_nodes.py``)
  unconditionally copied the freshly-built replacement node's
  ``comment_before``/``comment_inline`` (always ``None`` for a raw scalar
  payload) onto the mutated node, clobbering whatever comments the
  original parsed node carried. Fixed by dropping that copy so a "replace"
  mutation only changes ``type``/``value``/``children`` and leaves the
  target node's existing comments untouched.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    apply_single_tree_temp_mutation,
)
from ai_editor.core.tree_temp.yaml_emit import emit_yaml_source_from_roots
from ai_editor.core.tree_temp.yaml_frontend import parse_yaml_source_to_roots

_SOURCE = """\
# top comment
service:
  name: release-1669-check  # inline comment
  ports:
    - 8080  # http
    - 8443  # https
# trailing comment
"""


def _mutate_and_emit() -> str:
    roots = parse_yaml_source_to_roots(_SOURCE)
    apply_single_tree_temp_mutation(
        roots,
        "yaml",
        {
            "action": "replace",
            "json_pointer": "/service/name",
            "value": "release-1669-check-2",
        },
    )
    return emit_yaml_source_from_roots(roots)


def test_unrelated_scalar_edit_preserves_inline_comment_on_mapping_entry() -> None:
    """The ``name`` entry's own inline comment must survive an unrelated edit.

    Bug 20b4ba84 residual, symptom 1: replacing ``/service/name``'s value
    must not delete the ``# inline comment`` that was attached to that same
    line -- editing a value is not a license to drop its comment.
    """
    mutated = _mutate_and_emit()
    name_lines = [ln for ln in mutated.splitlines() if ln.strip().startswith("name:")]
    assert name_lines, f"no 'name:' line found in output:\n{mutated}"
    assert "# inline comment" in name_lines[0], (
        f"inline comment lost from mutated 'name' line: {name_lines[0]!r}\n"
        f"full output:\n{mutated}"
    )


def test_unrelated_scalar_edit_keeps_trailing_comment_after_last_sequence_item() -> (
    None
):
    """The document's trailing comment must land after the whole sequence.

    Bug 20b4ba84 residual, symptom 2: the trailing ``# trailing comment``
    must not be mis-attached into the middle of the ``ports`` sequence
    (between the ``8080`` and ``8443`` items); it must appear after the
    last item (``8443``), at (or after) document end.
    """
    mutated = _mutate_and_emit()
    lines = mutated.splitlines()

    def _index_of(needle: str) -> int:
        for i, ln in enumerate(lines):
            if needle in ln:
                return i
        raise AssertionError(f"line containing {needle!r} not found in:\n{mutated}")

    idx_8080 = _index_of("8080")
    idx_8443 = _index_of("8443")
    idx_trailing = _index_of("# trailing comment")

    assert idx_8080 < idx_8443, f"sequence items out of order:\n{mutated}"
    assert idx_trailing > idx_8443, (
        "trailing comment mis-attached before/inside the sequence "
        f"(expected after line {idx_8443}, got line {idx_trailing}):\n{mutated}"
    )


def test_unrelated_scalar_edit_preserves_all_comments_byte_level() -> None:
    """Combined check: every comment in the fixture must still be present."""
    mutated = _mutate_and_emit()
    for expected_comment in (
        "# top comment",
        "# inline comment",
        "# http",
        "# https",
        "# trailing comment",
    ):
        assert (
            expected_comment in mutated
        ), f"lost comment: {expected_comment!r}\n{mutated}"
