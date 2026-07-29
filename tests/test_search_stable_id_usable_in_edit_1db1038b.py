"""Bug 1db1038b: search-issued stable_ids must stay usable inside one edit batch.

Mirrors the ``search_stable_id_usable_in_edit_1db1038b`` pipeline scenario:
``universal_file_open`` -> ``universal_file_search`` for ``Name[name=query_object]``
-> ONE ``universal_file_edit`` batch replacing the last two matches.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"

_FIXTURE = (
    '"""Fixture module for bug 1db1038b (search-then-edit same-session '
    'stale id)."""\n'
    "\n"
    "\n"
    "def compute(query_object: int) -> int:\n"
    '    """Compute a value from the query object.\n'
    "\n"
    "    Args:\n"
    "        query_object: Input fixture value.\n"
    "\n"
    "    Returns:\n"
    "        Computed fixture value.\n"
    '    """\n'
    "    return query_object + query_object\n"
)


@pytest.mark.asyncio
async def test_search_stable_ids_usable_in_next_edit_batch(tmp_path) -> None:
    """Both stable_ids from one search must apply in the very next edit batch."""
    rel = "verify/1db1038b_search_stable_id_usable_in_edit.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_FIXTURE.encode("utf-8"),
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
                        "search_type": "simple",
                        "node_type": "Name",
                        "name": "query_object",
                    }
                )
            )
            assert isinstance(search, SuccessResult), getattr(
                search, "message", search
            )
            matches = list(search.data.get("matches") or [])
            assert len(matches) >= 2, matches
            stable_ids = [str(m["stable_id"]) for m in matches[-2:]]

            edit = await edit_cmd.execute(
                project_id=_PROJECT_UUID,
                session_id=sid,
                file_path=rel,
                operations=[
                    {
                        "type": "replace",
                        "node_id": stable_ids[0],
                        "code_lines": ["query_object"],
                    },
                    {
                        "type": "replace",
                        "node_id": stable_ids[1],
                        "code_lines": ["query_object"],
                    },
                ],
            )
    finally:
        release_session(sid)

    assert not isinstance(edit, ErrorResult), {
        "message": getattr(edit, "message", None),
        "details": getattr(edit, "details", None),
        "stable_ids": stable_ids,
    }
    assert isinstance(edit, SuccessResult), edit


@pytest.mark.asyncio
async def test_search_stable_ids_survive_shifting_replacement(tmp_path) -> None:
    """Second op's search-issued stable_id survives a length-changing first op."""
    rel = "verify/1db1038b_shift.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_FIXTURE.encode("utf-8"),
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
                        "search_type": "simple",
                        "node_type": "Name",
                        "name": "query_object",
                    }
                )
            )
            assert isinstance(search, SuccessResult), getattr(
                search, "message", search
            )
            matches = list(search.data.get("matches") or [])
            assert len(matches) >= 2, matches
            stable_ids = [str(m["stable_id"]) for m in matches[-2:]]

            edit = await edit_cmd.execute(
                project_id=_PROJECT_UUID,
                session_id=sid,
                file_path=rel,
                operations=[
                    {
                        "type": "replace",
                        "node_id": stable_ids[0],
                        "code_lines": ["renamed_object_value"],
                    },
                    {
                        "type": "replace",
                        "node_id": stable_ids[1],
                        "code_lines": ["renamed_object_value"],
                    },
                ],
            )
    finally:
        release_session(sid)

    assert not isinstance(edit, ErrorResult), {
        "message": getattr(edit, "message", None),
        "details": getattr(edit, "details", None),
        "stable_ids": stable_ids,
    }
    assert isinstance(edit, SuccessResult), edit
