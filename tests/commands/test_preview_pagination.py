from __future__ import annotations

from ai_editor.commands.universal_file_preview.preview_pagination import (
    apply_preview_pagination,
    serialize_preview_envelope,
)


def test_preview_pagination_fits_without_chunk() -> None:
    envelope = {
        "focus": {"node_ref": "root", "node_kind": "mapping"},
        "selector_applied": None,
        "total_blocks": 1,
        "blocks": [{"node_ref": "a", "summary": {"name": "x"}}],
    }
    result = apply_preview_pagination(envelope, offset=0, max_chars=10_000)
    assert result["blocks"] == envelope["blocks"]
    assert result["preview_has_more"] is False
    assert result["preview_next_offset"] is None
    assert result["preview_total_chars"] == len(serialize_preview_envelope(envelope))


def test_preview_pagination_returns_chunk_when_large() -> None:
    envelope = {
        "focus": {"node_ref": "root"},
        "selector_applied": None,
        "total_blocks": 1,
        "blocks": [{"node_ref": "a", "text": "x" * 500}],
    }
    serialized = serialize_preview_envelope(envelope)
    result = apply_preview_pagination(envelope, offset=0, max_chars=100)
    assert result["preview_has_more"] is True
    assert result["preview_next_offset"] == 100
    assert result["preview_chunk"] == serialized[:100]
    assert "blocks" not in result


def test_preview_pagination_offset_page() -> None:
    envelope = {"focus": {"node_ref": "root"}, "blocks": [{"text": "y" * 200}]}
    serialized = serialize_preview_envelope(envelope)
    page = apply_preview_pagination(envelope, offset=50, max_chars=80)
    assert page["preview_chunk"] == serialized[50:130]
    assert page["preview_has_more"] == (130 < len(serialized))
