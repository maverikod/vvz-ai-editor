"""Regression tests for the canonical live pipeline helper."""

from __future__ import annotations

from typing import Any

import pytest

from scripts import verify_editor_ca_chain as pipeline


@pytest.mark.asyncio
async def test_read_file_text_omits_end_line_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default readback must not synthesize an out-of-bounds end_line."""
    seen: dict[str, Any] = {}

    async def fake_call(
        _client: object,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen["command"] = command
        seen["params"] = params or {}
        return {"lines": [{"content": "one"}, {"content": "two"}]}

    monkeypatch.setattr(pipeline, "_call", fake_call)

    text = await pipeline._read_file_text(
        object(),
        "project-1",
        "verify/small.txt",
    )

    assert text == "one\ntwo"
    assert seen["command"] == "get_file_lines"
    assert seen["params"] == {
        "project_id": "project-1",
        "file_path": "verify/small.txt",
        "start_line": 1,
        "allow_healthy_line_ops": True,
    }


@pytest.mark.asyncio
async def test_read_file_text_uses_explicit_short_end_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenarios with known fixture length may request an in-bounds end_line."""
    seen: dict[str, Any] = {}

    async def fake_call(
        _client: object,
        _command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen["params"] = params or {}
        return {"lines": ["only"]}

    monkeypatch.setattr(pipeline, "_call", fake_call)

    text = await pipeline._read_file_text(
        object(),
        "project-1",
        "verify/small.txt",
        end_line=1,
    )

    assert text == "only"
    assert seen["params"]["end_line"] == 1
