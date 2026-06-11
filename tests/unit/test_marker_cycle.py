"""
Unit tests for EditSession marker denude/restore cycle (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.edit_session.marker_cycle import (
    denude_marked_tree,
    restore_marked_tree,
)
from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.core.tree_lifecycle.checksum import compute_content_checksum
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file


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
