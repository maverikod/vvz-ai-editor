"""Unit tests for ai_editor.tree.preview_selector (G-004)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_editor.tree.contracts import NodeId
from ai_editor.tree.preview_selector import (
    PreviewRenderMode,
    PreviewSelector,
    PreviewSelectorConfig,
    paginate_envelope,
)


@dataclass(frozen=True)
class _Block:
    short_id: NodeId
    text: str


_BLOCKS = (
    _Block(NodeId(1), "a"),
    _Block(NodeId(2), "b"),
    _Block(NodeId(3), "c"),
    _Block(NodeId(4), "d"),
    _Block(NodeId(5), "e"),
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (":", (None, None)),
        ("3:", (3, None)),
        (":5", (None, 5)),
    ],
)
def test_preview_selector_parse_slice(
    raw: str, expected: tuple[int | None, int | None]
) -> None:
    selector = PreviewSelector.parse(raw)
    assert selector._kind == "slice"
    assert selector._slice_start == expected[0]
    assert selector._slice_end == expected[1]


def test_preview_selector_parse_cherry_pick_short_ids() -> None:
    selector = PreviewSelector.parse([3, 1])
    assert selector._kind == "ids"
    assert selector._short_ids == (NodeId(3), NodeId(1))
    applied = selector.apply(_BLOCKS)
    assert [block.short_id for block in applied] == [NodeId(3), NodeId(1)]


def test_preview_selector_apply_slice_bounds() -> None:
    assert len(PreviewSelector.parse(":").apply(_BLOCKS)) == 5
    assert len(PreviewSelector.parse("3:").apply(_BLOCKS)) == 2
    assert len(PreviewSelector.parse(":5").apply(_BLOCKS)) == 5
    assert len(PreviewSelector.parse("1:4").apply(_BLOCKS)) == 3


@pytest.mark.parametrize(
    ("line_span", "threshold", "expected"),
    [
        (199, 200, PreviewRenderMode.INLINE),
        (200, 200, PreviewRenderMode.DRILLDOWN),
        (0, 0, PreviewRenderMode.DRILLDOWN),
    ],
)
def test_decide_render_mode(
    line_span: int, threshold: int, expected: PreviewRenderMode
) -> None:
    config = PreviewSelectorConfig(full_text_max_lines={"python": threshold})
    mode = PreviewSelector.decide_render_mode(
        format_key="python",
        line_span=line_span,
        config=config,
    )
    assert mode is expected


def test_paginate_envelope_truncates_with_ellipsis() -> None:
    text = "abcdefghij"
    assert paginate_envelope(text, max_chars=5) == "abcde\u2026"
    assert paginate_envelope(text, max_chars=20) == text
    assert paginate_envelope(text, max_chars=None) == text
