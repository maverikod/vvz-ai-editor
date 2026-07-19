"""Tests for universal_file_node_at_line command."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.node_at_line_command import (
    LINE_NOT_FOUND,
    UniversalFileNodeAtLineCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from tests.fixtures.validation_passing_python import SEARCH_MODULE
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"

_TRY_BRANCHES = """try:
    risky()
except ValueError:
    recover()
else:
    succeed()
finally:
    cleanup()
"""


@pytest.mark.asyncio
async def test_node_at_line_returns_short_id_for_function_body(tmp_path) -> None:
    rel = "src/at_line.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = UniversalFileNodeAtLineCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "line": 12,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    node_ref = res.data.get("node_ref")
    assert isinstance(node_ref, int) or isinstance(node_ref, str)
    assert res.data.get("type")
    assert res.data["start_line"] <= 12 <= res.data["end_line"]


@pytest.mark.asyncio
async def test_node_at_line_include_ancestors(tmp_path) -> None:
    rel = "src/at_line2.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = UniversalFileNodeAtLineCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "line": 12,
                        "include_ancestors": True,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, SuccessResult)
    ancestors = res.data.get("ancestors") or []
    assert ancestors
    spans = [
        (res.data["end_line"] - res.data["start_line"])
    ] + [(a["end_line"] - a["start_line"]) for a in ancestors]
    assert spans == sorted(spans)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("line", "expected_type"),
    [(1, "Try"), (3, "ExceptHandler"), (5, "Else"), (7, "Finally")],
)
async def test_node_at_line_preserves_try_branch_addressability(
    tmp_path, line: int, expected_type: str
) -> None:
    rel = "src/try_branches.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_TRY_BRANCHES.encode("utf-8"),
    )
    cmd = UniversalFileNodeAtLineCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "line": line,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert res.data["type"] == expected_type
    assert res.data["node_ref"]
    assert res.data["start_line"] <= line <= res.data["end_line"]


@pytest.mark.asyncio
async def test_node_at_line_not_found(tmp_path) -> None:
    rel = "src/empty.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b'"""Doc."""\n\n\n',
    )
    cmd = UniversalFileNodeAtLineCommand()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            res = await cmd.execute(
                **cmd.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "line": 14,
                    }
                )
            )
    finally:
        release_session(sid)

    assert isinstance(res, ErrorResult)
    assert res.code == LINE_NOT_FOUND
