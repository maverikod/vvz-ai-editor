"""Regression test for bug b215fbd3: tree-temp YAML mutation preserves style.

A single top-level insert via the tree-temp mutation API must not touch any
line beyond the newly inserted one: comments, double/single-quoted scalars,
and inline flow-style mappings on untouched nodes must survive byte-for-byte
against a zero-edit round-trip baseline (comment-rich source, quote/flow
style preservation across an actual mutation -- not just parse+re-emit).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    apply_single_tree_temp_mutation,
)
from ai_editor.core.tree_temp.yaml_emit import emit_yaml_source_from_roots
from ai_editor.core.tree_temp.yaml_frontend import parse_yaml_source_to_roots

_SOURCE = """# section banner
title: "Hello"        # double-quoted scalar
tags: {a: 1, b: 2}     # flow-style inline map
nested:
  inner: 'single'      # single-quoted scalar
  # a comment before this list
  items:
    - one
    - two
"""


def test_yaml_insert_one_key_preserves_untouched_style_and_comments() -> None:
    """Inserting one new top-level key must not alter any other line.

    Compares the mutated output against a zero-edit round-trip baseline
    (parse then immediately re-emit, no mutation) rather than the raw
    source text, so the assertion isolates the effect of the insert
    operation itself from any pre-existing, unrelated round-trip
    normalization.
    """
    baseline_roots = parse_yaml_source_to_roots(_SOURCE)
    baseline = emit_yaml_source_from_roots(baseline_roots)
    baseline_lines = baseline.splitlines()

    mutated_roots = parse_yaml_source_to_roots(_SOURCE)
    apply_single_tree_temp_mutation(
        mutated_roots,
        "yaml",
        {
            "action": "insert",
            "parent_json_pointer": "",
            "key": "added",
            "value": "new-value",
            "position": "last",
        },
    )
    mutated = emit_yaml_source_from_roots(mutated_roots)
    mutated_lines = mutated.splitlines()

    # Every baseline line survives untouched, in order, as a prefix of the
    # mutated output -- a targeted mutation, not a full-file rewrite.
    assert mutated_lines[: len(baseline_lines)] == baseline_lines

    # Exactly one new line was appended for the inserted key.
    assert len(mutated_lines) == len(baseline_lines) + 1
    assert mutated_lines[-1].startswith("added:")
    assert "new-value" in mutated_lines[-1]

    # Comment, quote-style, and flow-style spot checks survive the mutation.
    assert "# section banner" in mutated
    assert '"Hello"' in mutated
    assert "# double-quoted scalar" in mutated
    assert "{a: 1, b: 2}" in mutated
    assert "# flow-style inline map" in mutated
    assert "'single'" in mutated
    assert "# single-quoted scalar" in mutated
    assert "# a comment before this list" in mutated


def test_yaml_zero_edit_roundtrip_is_stable() -> None:
    """Parsing then re-emitting with no mutation reproduces the same text twice.

    Guards against the new flow_style/quote-preservation machinery
    introducing nondeterminism on an unmutated document.
    """
    roots_a = parse_yaml_source_to_roots(_SOURCE)
    roots_b = parse_yaml_source_to_roots(_SOURCE)
    out_a = emit_yaml_source_from_roots(roots_a)
    out_b = emit_yaml_source_from_roots(roots_b)
    assert out_a == out_b
