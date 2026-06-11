"""Tree-temp edit session preview must reflect draft state before commit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    draft_path_for,
)
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_preview.session import (
    merge_edit_session_into_preview_params,
)
from ai_editor.core.tree_temp.tree_node import TreeNode
from ai_editor.core.yaml_tree import tree_builder as ytb
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    mock_upstream,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_YAML_PID = "a1a1a1a1-1111-4111-8111-111111111111"
_JSON_PID = "b2b2b2b2-2222-4222-8222-222222222222"
_YAML_REL = "plans/step.yaml"
_JSON_REL = "cfg/app.json"
_YAML_BODY = (
    b"step_id: G-007\n"
    b"name: session cleanup\n"
    b"source_ranges:\n"
    b"  - start: 97\n"
    b"    end: 107\n"
)


@pytest.fixture(autouse=True)
def _reset_yaml_trees() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _YAML_REL, _JSON_REL)
    ytb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _YAML_REL, _JSON_REL)
    ytb._trees.clear()


def test_merge_edit_session_injects_draft_path_for_tree_temp(tmp_path: Path) -> None:
    """FORMAT_TREE_TEMP sessions bind preview to draft_path, not stale disk source."""
    src = tmp_path / "cfg.yaml"
    src.write_text("a: 1\n", encoding="utf-8")
    descriptor = FormatDescriptor(
        format_group=FORMAT_TREE_TEMP,
        handler_id="yaml",
        draft_path=draft_path_for(src, FORMAT_TREE_TEMP),
        lockfile_path=src.with_suffix(src.suffix + ".write"),
        available_operations=["insert", "delete", "replace"],
    )
    edit_sess = create_session(
        abs_path=src,
        descriptor=descriptor,
        file_path="cfg.yaml",
        tree_id=None,
        tree_temp_roots=[
            TreeNode(stable_id="00000000-0000-4000-8000-000000000001", type="object")
        ],
        ca_session_id="test-ca-1",
    )
    try:
        merged = merge_edit_session_into_preview_params(
            {
                "project_id": "p",
                "file_path": "cfg.yaml",
                "session_id": edit_sess.session_id,
            }
        )
        assert merged["_preview_abs_path"] == str(edit_sess.draft_path)
        assert "tree_id" not in merged
    finally:
        release_session(edit_sess.session_id)


async def _open_yaml(tmp: Path) -> tuple[str, Path, Path, object]:
    return await open_ca_file(
        tmp,
        project_id=_YAML_PID,
        file_path=_YAML_REL,
        content=_YAML_BODY,
    )


def _range_starts_from_blocks(data: dict[str, Any]) -> list[int]:
    blocks = cast(list[dict[str, Any]], data.get("blocks") or [])
    starts: list[int] = []
    for block in blocks:
        summary = cast(dict[str, Any], block.get("summary") or {})
        names = cast(list[str], summary.get("key_names") or [])
        values = cast(list[str], summary.get("key_values") or [])
        if "start" in names:
            idx = names.index("start")
            starts.append(int(values[idx]))
    return starts


def _range_starts_from_focus(data: dict[str, Any]) -> list[int]:
    """Extract YAML ``start`` values from preview focus text or blocks."""
    focus = cast(dict[str, Any], data.get("focus") or {})
    text = str(focus.get("text") or "")
    if text:
        return [int(x) for x in re.findall(r"start: (\d+)", text)]
    return _range_starts_from_blocks(data)


def _preview_params(
    project_id: str,
    rel: str,
    session_id: str | None = None,
    node_ref: str | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "project_id": project_id,
        "file_path": rel,
    }
    if session_id is not None:
        raw["session_id"] = session_id
    if node_ref is not None:
        raw["node_ref"] = node_ref
    return raw


async def _run_preview(
    workspace: Path,
    upstream: object,
    params: dict[str, Any],
) -> object:
    preview = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        return await preview.execute(**params)


@pytest.mark.asyncio
async def test_yaml_tree_temp_insert_visible_in_session_preview(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _open_yaml(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/source_ranges",
                            "index": 0,
                            "value": {"start": 5, "end": 7},
                        }
                    ],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult)
        assert edit_res.data.get("updated") is True

        prev = await _run_preview(
            workspace,
            upstream,
            _preview_params(_YAML_PID, _YAML_REL, sid, "/source_ranges"),
        )
        await close.execute(
            **close.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                }
            )
        )

    assert isinstance(prev, SuccessResult)
    assert _range_starts_from_focus(cast(dict[str, Any], prev.data)) == [5, 97]


@pytest.mark.asyncio
async def test_yaml_tree_temp_replace_visible_in_session_preview(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _open_yaml(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [
                                {"start": 5, "end": 7},
                                {"start": 97, "end": 107},
                            ],
                        }
                    ],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult)
        assert edit_res.data.get("updated") is True

        prev = await _run_preview(
            workspace,
            upstream,
            _preview_params(_YAML_PID, _YAML_REL, sid, "/source_ranges"),
        )
        await close.execute(
            **close.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                }
            )
        )

    assert isinstance(prev, SuccessResult)
    assert _range_starts_from_focus(cast(dict[str, Any], prev.data)) == [5, 97]


async def _open_json(tmp: Path) -> tuple[str, Path, Path, object]:
    content = json.dumps({"source_ranges": [{"start": 97, "end": 107}]}).encode()
    return await open_ca_file(
        tmp,
        project_id=_JSON_PID,
        file_path=_JSON_REL,
        content=content,
    )


async def _scalar_preview_value(
    workspace: Path,
    upstream: object,
    project_id: str,
    rel: str,
    session_id: str,
    node_ref: str,
) -> str:
    preview = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await preview.execute(
            **_preview_params(project_id, rel, session_id, node_ref)
        )
    assert isinstance(res, SuccessResult)
    focus = cast(dict[str, Any], res.data["focus"])
    return str(cast(dict[str, Any], focus.get("attributes") or {}).get("value"))


@pytest.mark.asyncio
async def test_json_tree_temp_preview_matches_draft(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _open_json(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _JSON_PID,
                    "session_id": sid,
                    "file_path": _JSON_REL,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/source_ranges",
                            "index": 0,
                            "value": {"start": 5, "end": 7},
                        }
                    ],
                }
            )
        )
        prev_insert = await _run_preview(
            workspace,
            upstream,
            _preview_params(_JSON_PID, _JSON_REL, sid, "/source_ranges"),
        )
        insert_first = await _scalar_preview_value(
            workspace, upstream, _JSON_PID, _JSON_REL, sid, "/source_ranges/0/start"
        )
        insert_second = await _scalar_preview_value(
            workspace, upstream, _JSON_PID, _JSON_REL, sid, "/source_ranges/1/start"
        )
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _JSON_PID,
                    "session_id": sid,
                    "file_path": _JSON_REL,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [
                                {"start": 5, "end": 7},
                                {"start": 97, "end": 107},
                                {"start": 200, "end": 210},
                            ],
                        }
                    ],
                }
            )
        )
        prev_replace = await _run_preview(
            workspace,
            upstream,
            _preview_params(_JSON_PID, _JSON_REL, sid, "/source_ranges"),
        )
        await close.execute(
            **close.validate_params(
                {
                    "project_id": _JSON_PID,
                    "session_id": sid,
                    "file_path": _JSON_REL,
                }
            )
        )

    assert isinstance(prev_insert, SuccessResult)
    assert int(insert_first) == 5
    assert int(insert_second) == 97

    assert isinstance(prev_replace, SuccessResult)
    assert cast(dict[str, Any], prev_replace.data).get("total_blocks") == 3


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
        await close.execute(
            **close.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "file_path": _YAML_REL,
                }
            )
        )

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
