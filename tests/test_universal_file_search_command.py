"""Tests for universal_file_search on open Python edit sessions."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_MODULE = '''"""Search test module."""

def foo() -> int:
    """Return one."""
    return 1
'''


@pytest.mark.asyncio
async def test_search_xpath_finds_function_def(tmp_path) -> None:
    rel = "src/search_me.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_MODULE.encode("utf-8"),
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
    assert matches[0].get("node_ref")
    assert matches[0].get("name") == "foo"
