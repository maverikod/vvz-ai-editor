"""
Tests for CST anchor verification.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest

from ai_editor.commands.anchor_check import AnchorMismatch, check_cst_anchor
from ai_editor.core.cst_tree.tree_builder import load_file_to_tree, remove_tree


def _stable_id_at_line(py_file: Path, line: int) -> str:
    tree = load_file_to_tree(str(py_file))
    try:
        node = min(
            (
                meta
                for meta in tree.metadata_map.values()
                if meta.start_line <= line <= meta.end_line
            ),
            key=lambda meta: (meta.end_line - meta.start_line, meta.start_line),
        )
        return cast(str, node.stable_id)
    finally:
        remove_tree(tree.tree_id)


class TestCSTAnchor:
    def test_check_cst_anchor_sidecar_present_correct_stable_id_passes(
        self, tmp_path: Path
    ) -> None:
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            "def alpha():\n    return 1\n\n",
            encoding="utf-8",
        )
        stable_id = _stable_id_at_line(py_file, 2)

        check_cst_anchor(py_file, 2, stable_id)

    def test_check_cst_anchor_sidecar_present_wrong_stable_id_raises(
        self, tmp_path: Path
    ) -> None:
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            "def alpha():\n    return 1\n\n",
            encoding="utf-8",
        )
        _stable_id_at_line(py_file, 2)

        with pytest.raises(AnchorMismatch) as exc_info:
            check_cst_anchor(py_file, 2, "wrong-stable-id")

        assert exc_info.value.details["anchor_field"] == "anchor_node_id"
        assert exc_info.value.details["expected"] == "wrong-stable-id"

    def test_check_cst_anchor_sidecar_absent_warns_and_passes(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        py_file = tmp_path / "mod.py"
        py_file.write_text("x = 1\n", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            check_cst_anchor(py_file, 1, "stable-id")

        assert "sidecar not found" in caplog.text
