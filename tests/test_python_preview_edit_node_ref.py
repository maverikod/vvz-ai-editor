"""Regression: Python preview node_ref must resolve in edit (EDITOR-BUG-001)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.core.edit_session.edit_session import SessionTreeValidity
from ai_editor.core.edit_session.edit_operations_adapter import session_has_map_tree
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    open_ca_file,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_SAMPLE = '''"""Sample module for workflow test."""
from __future__ import annotations


def alpha() -> int:
    return 1
'''


@pytest.fixture(autouse=True)
def _reset_ca() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)


async def _preview(
    workspace: Path, upstream: object, sid: str, rel: str
) -> SuccessResult:
    cmd = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(
            project_id=_PROJECT_UUID,
            file_path=rel,
            session_id=sid,
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return res


def _alpha_block(blocks: list[dict]) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == "function":
            attrs = str(summary.get("attribute_summary") or "")
            if "name='alpha'" in attrs or "FunctionDef" in attrs:
                return block
    return next(b for b in blocks if (b.get("summary") or {}).get("type") == "function")


def _internal_node_id_from_block(block: dict) -> str:
    attrs = str((block.get("summary") or {}).get("attribute_summary") or "")
    prefix = "internal_node_id='"
    start = attrs.find(prefix)
    assert start != -1, attrs
    start += len(prefix)
    end = attrs.find("'", start)
    assert end != -1, attrs
    return attrs[start:end]


def _docstring_block(blocks: list[dict]) -> dict:
    for block in blocks:
        text = str(block.get("text") or "")
        if "Sample module" in text or "workflow test" in text:
            return block
    return blocks[0]


@pytest.mark.asyncio
async def test_python_open_builds_map_tree(tmp_path: Path) -> None:
    rel = "wf_test/sample.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_SAMPLE.encode(),
    )
    sess = get_session(sid, rel)
    assert sess.core.tree_validity == SessionTreeValidity.VALID
    assert session_has_map_tree(sess.core)


@pytest.mark.asyncio
async def test_python_preview_internal_node_id_stable_across_calls(
    tmp_path: Path,
) -> None:
    rel = "wf_test/sample.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_SAMPLE.encode(),
    )
    first = await _preview(workspace, upstream, sid, rel)
    second = await _preview(workspace, upstream, sid, rel)
    alpha1 = _alpha_block(list(first.data.get("blocks") or []))
    alpha2 = _alpha_block(list(second.data.get("blocks") or []))
    id1 = (alpha1.get("summary") or {}).get("attribute_summary", "")
    id2 = (alpha2.get("summary") or {}).get("attribute_summary", "")
    assert "internal_node_id=" in id1
    assert id1 == id2
    assert alpha1["node_ref"] == alpha2["node_ref"]


@pytest.mark.asyncio
async def test_python_edit_accepts_preview_node_ref_without_stale_id(
    tmp_path: Path,
) -> None:
    rel = "wf_test/sample.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_SAMPLE.encode(),
    )
    preview = await _preview(workspace, upstream, sid, rel)
    alpha_ref = str(_alpha_block(list(preview.data.get("blocks") or []))["node_ref"])

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": alpha_ref,
                            "code_lines": [
                                "def alpha() -> int:",
                                "    return 100",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert getattr(res, "code", None) != "STALE_NODE_ID"

    draft = get_session(sid, rel).core.session_source_path.read_text(encoding="utf-8")
    assert "return 100" in draft
    assert "    return 1\n" not in draft

    preview2 = await _preview(workspace, upstream, sid, rel)
    alpha_after_ref = str(
        _alpha_block(list(preview2.data.get("blocks") or []))["node_ref"]
    )
    with upstream_context(workspace=workspace, upstream=upstream):
        res2 = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": alpha_after_ref,
                            "code_lines": [
                                "def alpha() -> int:",
                                "    return 200",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(res2, SuccessResult), getattr(res2, "message", res2)


@pytest.mark.asyncio
async def test_python_map_uuid_stable_for_untouched_nodes_after_edit(
    tmp_path: Path,
) -> None:
    rel = "wf_test/sample.py"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_SAMPLE.encode(),
    )
    preview = await _preview(workspace, upstream, sid, rel)
    blocks = list(preview.data.get("blocks") or [])
    doc_uuid_before = _internal_node_id_from_block(_docstring_block(blocks))
    alpha_ref = str(_alpha_block(blocks)["node_ref"])

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": alpha_ref,
                            "code_lines": [
                                "def alpha() -> int:",
                                "    return 100",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)

    preview2 = await _preview(workspace, upstream, sid, rel)
    blocks2 = list(preview2.data.get("blocks") or [])
    doc_uuid_after = _internal_node_id_from_block(_docstring_block(blocks2))
    assert doc_uuid_before == doc_uuid_after

    with upstream_context(workspace=workspace, upstream=upstream):
        res_by_uuid = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": doc_uuid_before,
                            "code_lines": ['"""Updated module doc."""'],
                        }
                    ],
                }
            )
        )
    assert isinstance(res_by_uuid, SuccessResult), getattr(res_by_uuid, "message", res_by_uuid)
