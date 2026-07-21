"""
Unit tests for EditSession marker denude/restore cycle (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_editor.core.edit_session.marker_cycle import (
    denude_marked_tree,
    restore_marked_tree,
)
from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.core.tree_lifecycle.checksum import compute_content_checksum
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file


def _build_python_marked_tree(tmp_path: Path, content: str) -> tuple[Path, Path, str]:
    name = "sample.py"
    source_abs = tmp_path / name
    source_abs.write_text(content, encoding="utf-8")
    checksum = compute_content_checksum(content)
    ref = TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=name,
        content_checksum=checksum,
    )
    marked_text = ref.sidecar_path.read_text(encoding="utf-8")
    return source_abs, ref.sidecar_path, marked_text


def test_python_map_short_ids_match_tree_markers_for_commented_statement(
    tmp_path: Path,
) -> None:
    """Regression bdce5d39 (secondary hazard): ``TreeBuilder.build`` MAP
    discovery for ``.py`` files must walk the SAME post-order marked TREE that
    ``mark()`` just produced (``PythonHandler.discover_marked_nodes``), not a
    separately-numbered ``parse_content()`` pass. Two unsynchronized short_id
    sequences let MAP entries point at markers that do not exist in the TREE
    section (or the reverse: a marker in TREE with no MAP entry), most visibly
    for a module-level statement carrying a real trailing comment.

    Every MAP short_id must have a matching ``# ___id___:N`` marker in TREE,
    and the ``Y = 0`` statement's own marker (whatever sid it was given) must
    be a MAP entry.
    """
    content = (
        '"""Module docstring."""\n\n'
        "Y = 0  # doc: anchor variable\n\n"
        "class Foo:  # type: ignore[misc]\n"
        '    """Foo docstring."""\n\n'
        "    def bar(self) -> None:  # note\n"
        '        """Bar docstring."""\n'
        "        pass\n"
    )
    _source_abs, _sidecar, marked = _build_python_marked_tree(tmp_path, content)
    sections = parse_tree_file(marked)
    tree_text = sections.tree

    for entry in sections.map.entries:
        marker = f"# ___id___:{entry.short_id}"
        assert marker in tree_text, (
            f"MAP entry short_id={entry.short_id} kind={entry.kind!r} "
            f"has no matching marker in TREE:\n{tree_text}"
        )

    y_line = next(
        (line for line in tree_text.splitlines() if line.lstrip().startswith("Y = 0")),
        None,
    )
    assert y_line is not None, f"Y = 0 statement missing from TREE:\n{tree_text}"
    match = re.search(r"# ___id___:(\d+)", y_line)
    assert match is not None, f"Y = 0 line has no ___id___ marker: {y_line!r}"
    y_sid = int(match.group(1))
    by_short = {entry.short_id: entry for entry in sections.map.entries}
    assert y_sid in by_short, (
        f"Y = 0 marker sid={y_sid} has no MAP entry "
        f"(known short_ids: {sorted(by_short)})"
    )


def _build_json_marked_tree(tmp_path: Path) -> tuple[Path, Path, str]:
    name = "sample.json"
    source_abs = tmp_path / name
    content = '{"alpha": 1, "beta": 2}\n'
    source_abs.write_text(content, encoding="utf-8")
    checksum = compute_content_checksum(content)
    ref = TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=name,
        content_checksum=checksum,
    )
    marked_text = ref.sidecar_path.read_text(encoding="utf-8")
    return source_abs, ref.sidecar_path, marked_text


def test_denude_restore_preserves_map_uuids(tmp_path: Path) -> None:
    source_abs, _sidecar, marked = _build_json_marked_tree(tmp_path)
    before = parse_tree_file(marked)
    before_uuids = sorted(e.uuid for e in before.map.entries)
    before_next_free = before.map.next_free
    denuded, state = denude_marked_tree(source_abs=source_abs, marked_tree=marked)
    assert state.map_section == before.map
    restored = restore_marked_tree(
        source_abs=source_abs,
        denuded_after_mutation=denuded,
        state=state,
    )
    after = parse_tree_file(restored)
    after_uuids = sorted(e.uuid for e in after.map.entries)
    assert before_uuids == after_uuids
    assert after.map.next_free == before_next_free
    assert after.checksums == before.checksums


def test_restore_uses_prior_map_next_free(tmp_path: Path) -> None:
    source_abs, _sidecar, marked = _build_json_marked_tree(tmp_path)
    sections = parse_tree_file(marked)
    prior_next_free = sections.map.next_free
    denuded, state = denude_marked_tree(source_abs=source_abs, marked_tree=marked)
    restored = restore_marked_tree(
        source_abs=source_abs,
        denuded_after_mutation=denuded,
        state=state,
    )
    restored_sections = parse_tree_file(restored)
    assert restored_sections.map.next_free == prior_next_free
    restored_by_short = {e.short_id: e for e in restored_sections.map.entries}
    for entry in sections.map.entries:
        restored_entry = restored_by_short[entry.short_id]
        assert restored_entry.uuid == entry.uuid
