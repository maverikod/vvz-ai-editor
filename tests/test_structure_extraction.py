"""Tests for shared structure extraction (no DB, no vectorization)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.structure_extraction import (
    extract_structure,
    find_smallest_block_containing_line,
)
from ai_editor.core.structure_extraction.format_registry import should_scan_path


def test_extractor_python_function_block_without_db(tmp_path: Path) -> None:
    py_path = tmp_path / "sample.py"
    content = "def hello():\n    return 1\n\nclass C:\n    pass\n"
    py_path.write_text(content, encoding="utf-8")
    doc = extract_structure(
        file_path=str(py_path),
        content=content,
        include_text=False,
        ensure_persisted_tree=True,
    )
    assert doc.format_group == "sidecar"
    assert doc.blocks
    block = find_smallest_block_containing_line(doc, 1)
    assert block is not None
    assert block.node_type == "FunctionDef"
    assert block.block_id


def test_scan_all_false_excludes_log() -> None:
    assert should_scan_path("logs/app.log", scan_all=False) is False
    assert should_scan_path("src/foo.py", scan_all=False) is True


def test_scan_all_true_allows_txt_not_log_by_default() -> None:
    assert should_scan_path("notes.txt", scan_all=True) is True
    assert should_scan_path("debug.log", scan_all=True, include_logs=False) is False
    assert should_scan_path("debug.log", scan_all=True, include_logs=True) is True


def test_extractor_matches_sidecar_when_present(tmp_path: Path) -> None:
    py_path = tmp_path / "mod.py"
    py_path.write_text("def f():\n    x = 1\n", encoding="utf-8")
    from ai_editor.core.cst_tree.tree_builder import load_file_to_tree, remove_tree

    tree = load_file_to_tree(str(py_path))
    remove_tree(tree.tree_id)

    disk_doc = extract_structure(
        file_path=str(py_path),
        content=py_path.read_text(encoding="utf-8"),
        source="disk",
    )
    mem_doc = extract_structure(
        file_path=str(py_path),
        content=py_path.read_text(encoding="utf-8"),
        source="disk",
    )
    assert disk_doc.blocks
    line2_disk = find_smallest_block_containing_line(disk_doc, 2)
    line2_mem = find_smallest_block_containing_line(mem_doc, 2)
    assert line2_disk is not None
    assert line2_mem is not None
    assert line2_disk.start_line == line2_mem.start_line
    assert line2_disk.end_line == line2_mem.end_line
