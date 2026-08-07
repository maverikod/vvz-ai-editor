"""Close of an uncommitted tree-temp draft is refused, not silently discarded.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Split out of ``test_tree_temp_edit_session_preview`` to keep both modules within
the project's file-length limit; the shared YAML fixture and preview helpers are
imported from it so there is exactly one definition of each.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from tests.test_tree_temp_edit_session_preview import (
    _YAML_BODY,
    _YAML_PID,
    _YAML_REL,
    _open_yaml,
    _preview_params,
    _reset_yaml_trees,
    _run_preview,
)
from tests.thin_editor_ca_mocks import mock_upstream, upstream_context

__all__ = ["_reset_yaml_trees"]


@pytest.mark.asyncio
async def test_tree_temp_preview_without_commit_leaves_source_unchanged(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _open_yaml(tmp_path)
    before = origin.read_text(encoding="utf-8")
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/name",
                            "value": "edited name",
                        }
                    ],
                }
            )
        )
        prev = await _run_preview(
            workspace,
            upstream,
            _preview_params(_YAML_PID, _YAML_REL, sid, "/name"),
        )
        assert origin.read_text(encoding="utf-8") == before
        close_params = close.validate_params(
            {
                "project_id": _YAML_PID,
                "session_id": sid,
                "file_path": _YAML_REL,
            }
        )
        # The draft holds an uncommitted edit, so close must REFUSE it rather
        # than discard it: MODIFIED_NOT_WRITTEN exists so edits are never
        # silently dropped, and tree-temp sessions are no longer exempt.
        refused = await close.execute(**close_params)
        assert isinstance(refused, ErrorResult)
        assert refused.code == "MODIFIED_NOT_WRITTEN"
        # Refusing still leaves the external source untouched -- this test's point.
        assert origin.read_text(encoding="utf-8") == before
        # Drop the session without going through close, so the rest of the test
        # can re-open the file and prove the external source never changed.
        release_session(sid, _YAML_REL)

    stored = mock_upstream(origins={_YAML_REL: _YAML_BODY})
    with upstream_context(workspace=workspace, upstream=stored):
        after_close = await _run_preview(
            workspace,
            stored,
            _preview_params(_YAML_PID, _YAML_REL, node_ref="/name"),
        )

    assert isinstance(prev, SuccessResult)
    edited = cast(dict[str, Any], prev.data["focus"])
    edited_value = cast(dict[str, Any], edited.get("attributes") or {}).get("value")
    if edited_value != "edited name":
        assert "edited name" in str(edited.get("text") or "")
    assert isinstance(after_close, SuccessResult)
    reverted = cast(dict[str, Any], after_close.data["focus"])
    reverted_value = cast(dict[str, Any], reverted.get("attributes") or {}).get("value")
    if reverted_value != "session cleanup":
        assert "session cleanup" in str(reverted.get("text") or "")
