"""Regression: ``project_id`` is enforced on the session-scoped commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``universal_file_edit``, ``universal_file_write``, ``universal_file_search`` and
``universal_file_node_at_line`` declare ``project_id`` as required and used to
discard it (``del project_id`` / ``_ = project_id``), so an empty value and a
well-formed-but-wrong project UUID both returned full, correct results for a
file belonging to a different project. These tests pin the two stable codes the
guard now returns and prove the correct project id is still a happy path.
"""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.node_at_line_command import (
    UniversalFileNodeAtLineCommand,
)
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from tests.fixtures.validation_passing_python import SEARCH_MODULE
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_FOREIGN_PROJECT_UUID = "0badf00d-0bad-4f00-b00d-0badf00d0bad"
_REL = "src/scope_me.py"


def _params(command: str, project_id: str, sid: str) -> dict:
    """Otherwise-valid parameters for one command, with the project id swapped."""
    base: dict = {"project_id": project_id, "session_id": sid, "file_path": _REL}
    if command == "edit":
        base["operations"] = []
    elif command == "node_at_line":
        base["line"] = 1
    elif command == "search":
        base.update({"search_type": "xpath", "query": "FunctionDef[name='foo']"})
    elif command == "write":
        base["write_mode"] = "preview"
    return base


_COMMANDS = (
    ("edit", UniversalFileEditCommand),
    ("write", UniversalFileWriteCommand),
    ("search", UniversalFileSearchCommand),
    ("node_at_line", UniversalFileNodeAtLineCommand),
)


async def _run(name: str, command_cls: type, project_id: str, tmp_path):
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=_REL,
        content=SEARCH_MODULE.encode("utf-8"),
    )
    cmd = command_cls()
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            return await cmd.execute(**cmd.validate_params(_params(name, project_id, sid)))
    finally:
        release_session(sid)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,command_cls", _COMMANDS)
async def test_empty_project_id_is_validation_error(name, command_cls, tmp_path) -> None:
    """An empty project_id is rejected exactly as universal_file_open rejects it."""
    res = await _run(name, command_cls, "", tmp_path)
    assert isinstance(res, ErrorResult), res
    assert res.code == "VALIDATION_ERROR", (name, res.code, res.message)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,command_cls", _COMMANDS)
async def test_foreign_project_id_is_refused(name, command_cls, tmp_path) -> None:
    """A well-formed project id that does not own the session's file is refused.

    Code and message are the ones ``universal_file_preview`` already returns for
    this exact condition, so one condition keeps one answer across the surface.
    """
    res = await _run(name, command_cls, _FOREIGN_PROJECT_UUID, tmp_path)
    assert isinstance(res, ErrorResult), res
    assert res.code == "VALIDATION_ERROR", (name, res.code, res.message)
    assert str(res.message) == "session_id does not match project_id", res.message


@pytest.mark.asyncio
@pytest.mark.parametrize("name,command_cls", _COMMANDS)
async def test_owning_project_id_still_succeeds(name, command_cls, tmp_path) -> None:
    """The happy path is untouched: the owning project id still works."""
    res = await _run(name, command_cls, _PROJECT_UUID, tmp_path)
    assert isinstance(res, SuccessResult), getattr(res, "message", res)


@pytest.mark.asyncio
async def test_open_create_rejects_empty_project_id(tmp_path) -> None:
    """create=true issues zero CA calls, so open itself must reject the empty id.

    Without this the session would be registered owning no project at all, and
    the scope guard above would have nothing to compare against.
    """
    from tests.thin_editor_ca_mocks import make_workspace, mock_upstream

    workspace = make_workspace(tmp_path)
    upstream = mock_upstream(origins={})
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await UniversalFileOpenCommand().execute(
            session_id="ca-session-scope-open",
            project_id="",
            file_path=_REL,
            create=True,
            initial_content="x = 1\n",
        )
    assert isinstance(res, ErrorResult), res
    assert res.code == "VALIDATION_ERROR", (res.code, res.message)
