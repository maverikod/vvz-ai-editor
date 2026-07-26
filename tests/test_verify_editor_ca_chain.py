"""Regression tests for the canonical live pipeline helper."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import pytest

from scripts import verify_editor_ca_chain as pipeline


def test_available_checks_exposes_metadata_and_known_scenarios() -> None:
    """The unified ``pipeline`` CLI must expose stable check names."""
    checks = pipeline.available_checks()

    assert checks[0] == pipeline.METADATA_CHECK_NAME
    assert "open_queue_autopoll_84d93cca" in checks
    assert "styled_yaml_minimal_diff_b215fbd3" in checks


def test_resolve_requested_checks_rejects_unknown_name() -> None:
    """Unknown ``pipeline <check-name>`` arguments must fail loudly."""

    class Args:
        checks = ["does_not_exist"]

    with pytest.raises(pipeline.PipelineFailure) as exc_info:
        pipeline._resolve_requested_checks(Args())

    assert "Unknown pipeline checks requested" in str(exc_info.value)
    assert exc_info.value.evidence == {
        "unknown": ["does_not_exist"],
        "available": pipeline.available_checks(),
    }


def test_run_pipeline_honors_single_selected_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pipeline <check-name>`` must run only that named check."""
    seen: list[str] = []

    async def fake_run_scenario(
        name: str,
        _fn: object,
        _ca: object,
        _ed: object,
        _args: object,
        _watch_dir_id: str,
    ) -> dict[str, Any]:
        seen.append(name)
        return {"name": name, "status": "passed", "details": {}}

    async def fake_discover_watch_dir_id(_ca: object) -> dict[str, str]:
        return {"watch_dir_id": "watch-1", "source": "fake"}

    monkeypatch.setattr(pipeline, "_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(pipeline, "_discover_watch_dir_id", fake_discover_watch_dir_id)
    monkeypatch.setattr(pipeline, "_run_scenario", fake_run_scenario)

    args = argparse.Namespace(
        checks=["open_queue_autopoll_84d93cca"],
        watch_dir_id="",
        ca_host="ca-host",
        ca_port=15010,
        editor_host="editor-host",
        editor_port=15000,
        mtls_dir=pipeline.REPO_ROOT,
        list=False,
    )

    result = asyncio.run(pipeline.run_pipeline(args))

    assert seen == ["open_queue_autopoll_84d93cca"]
    assert result["requested_checks"] == ["open_queue_autopoll_84d93cca"]
    assert result["summary"] == {"passed": 1, "failed": 0, "total": 1}
    assert result["watch_dir"] == {
        "id": "watch-1",
        "source": "fake",
        "required": True,
    }


def test_read_file_text_sends_default_end_line_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_file_lines`` REQUIRES ``end_line``, so a default readback must always
    send a concrete value -- the generous ``_READ_FILE_TEXT_DEFAULT_END_LINE``
    -- when the caller does not know the file's exact line count."""
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

    text = asyncio.run(
        pipeline._read_file_text(
            object(),
            "project-1",
            "verify/small.txt",
        )
    )

    assert text == "one\ntwo"
    assert seen["command"] == "get_file_lines"
    assert seen["params"] == {
        "project_id": "project-1",
        "file_path": "verify/small.txt",
        "start_line": 1,
        "end_line": pipeline._READ_FILE_TEXT_DEFAULT_END_LINE,
        "allow_healthy_line_ops": True,
    }


def test_read_file_text_retries_on_invalid_range_with_total_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first-call INVALID_RANGE (end_line beyond the real file length) must
    retry once with the file's real ``total_lines`` taken from the error
    payload, instead of crashing on line-count surprises."""
    calls: list[dict[str, Any]] = []

    async def fake_call(
        _client: object,
        _command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append(params or {})
        if len(calls) == 1:
            raise pipeline.PipelineFailure(
                "get_file_lines rejected end_line",
                {"error": {"code": "INVALID_RANGE", "data": {"total_lines": 2}}},
            )
        return {"lines": [{"content": "one"}, {"content": "two"}]}

    monkeypatch.setattr(pipeline, "_call", fake_call)

    text = asyncio.run(
        pipeline._read_file_text(
            object(),
            "project-1",
            "verify/small.txt",
        )
    )

    assert text == "one\ntwo"
    assert [call["end_line"] for call in calls] == [
        pipeline._READ_FILE_TEXT_DEFAULT_END_LINE,
        2,
    ]


def test_read_file_text_uses_explicit_short_end_line(
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

    text = asyncio.run(
        pipeline._read_file_text(
            object(),
            "project-1",
            "verify/small.txt",
            end_line=1,
        )
    )

    assert text == "only"
    assert seen["params"]["end_line"] == 1
