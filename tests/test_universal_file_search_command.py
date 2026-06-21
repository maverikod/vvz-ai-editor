"""Tests for universal_file_search on open Python edit sessions."""

from __future__ import annotations

import re
import uuid

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from tests.fixtures.validation_passing_python import SEARCH_MODULE
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _foo_block(blocks: list[dict]) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == "function" and summary.get("name") == "foo":
            return block
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == "function":
            return block
    raise AssertionError("function block not found")


@pytest.mark.asyncio
async def test_search_xpath_finds_function_def(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = UniversalFileSearchCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "search_type": "xpath",
                        "query": "FunctionDef[name='foo']",
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    matches = res.data.get("matches") or []
    assert len(matches) >= 1
    assert isinstance(matches[0].get("node_ref"), int)
    assert matches[0].get("name") == "foo"


@pytest.mark.asyncio
async def test_search_node_ref_matches_preview_short_id(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    search_cmd = UniversalFileSearchCommand()
    preview_cmd = UniversalFilePreviewCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            preview = await preview_cmd.execute(
                project_id=_PROJECT_UUID,
                file_path=rel,
                session_id=sid,
            )
            assert isinstance(preview, SuccessResult), getattr(
                preview, "message", preview
            )
            preview_ref = _foo_block(list(preview.data.get("blocks") or []))["node_ref"]
            assert isinstance(preview_ref, int)

            search = await search_cmd.execute(
                **search_cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "search_type": "xpath",
                        "query": "FunctionDef[name='foo']",
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(search, SuccessResult), getattr(search, "message", search)
    match = (search.data.get("matches") or [])[0]
    assert match["node_ref"] == preview_ref
    assert isinstance(match["node_ref"], int)
    assert _UUID4_RE.match(str(match["stable_id"]))
    assert "node_ref_kind" not in match


@pytest.mark.asyncio
async def test_search_require_one_returns_int_node_ref(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = UniversalFileSearchCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "search_type": "xpath",
                        "query": "FunctionDef[name='foo']",
                        "require_one": True,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert isinstance(res.data.get("node_ref"), int)
    assert isinstance((res.data.get("match") or {}).get("node_ref"), int)


@pytest.mark.asyncio
async def test_search_non_unique_candidates_use_int_node_ref(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = UniversalFileSearchCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "search_type": "xpath",
                        "query": "//SimpleStatementLine",
                        "require_one": True,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, ErrorResult), res
    assert getattr(res, "code", None) == "NonUniqueMatch"
    candidates = (getattr(res, "details", None) or {}).get("candidates") or []
    assert candidates
    for candidate in candidates:
        assert isinstance(candidate.get("node_ref"), int)
        assert "node_ref_kind" not in candidate


@pytest.mark.asyncio
async def test_search_then_edit_using_node_ref(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    search_cmd = UniversalFileSearchCommand()
    edit_cmd = UniversalFileEditCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            search = await search_cmd.execute(
                **search_cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "search_type": "xpath",
                        "query": "FunctionDef[name='foo']",
                        "require_one": True,
                    }
                )
            )
            assert isinstance(search, SuccessResult), getattr(search, "message", search)
            node_ref = search.data["node_ref"]
            assert isinstance(node_ref, int)

            edit = await edit_cmd.execute(
                **edit_cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "operations": [
                            {
                                "type": "replace",
                                "node_id": str(node_ref),
                                "code_lines": [
                                    "def foo() -> int:",
                                    "    return 42",
                                ],
                            }
                        ],
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(edit, SuccessResult), getattr(edit, "message", edit)
    assert uuid.UUID(str((search.data.get("match") or {}).get("stable_id")))
