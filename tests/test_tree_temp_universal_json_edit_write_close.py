"""JSON tree-temp integration tests for universal_file_open/edit/write/close.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.core.json_tree import tree_builder as jtb
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.sibling_convention import sibling_tree_path
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    commit_write,
    materialize_tree_sidecar,
    mock_upstream,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_REL = "records/items.json"
_INIT = b'{"items":[{"id":1,"active":false}],"meta":{"tag":"old"}}\n'


def _clear() -> None:
    jtb._trees.clear()


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    _clear()
    yield
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    _clear()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _prep(
    tmp: Path, rel: str = _REL, content: bytes = _INIT
) -> tuple[str, Path, Path, object]:
    return await open_ca_file(
        tmp,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content,
    )


@pytest.mark.asyncio
async def test_replace_via_json_pointer_updates_draft_then_commits(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        er = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/items/0/active",
                            "value": True,
                        }
                    ],
                }
            )
        )
    assert isinstance(er, SuccessResult)
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
    )
    assert '"active": true' in origin.read_text(encoding="utf-8")
    sc = materialize_tree_sidecar(origin, file_path=_REL)
    sections = parse_tree_file(sc.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == _sha(origin.read_bytes())
    assert sections.tree.strip() != ""
    assert sections.map.next_free >= 1
    cl = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await cl.execute(
            **cl.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )


@pytest.mark.asyncio
async def test_delete_scalar_property_meta_tag(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [{"type": "delete", "json_pointer": "/meta/tag"}],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
    )
    data = json.loads(origin.read_text(encoding="utf-8"))
    assert "tag" not in data.get("meta", {})
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_insert_array_element_appends_via_append_semantics(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/items",
                            "value": {"id": 2, "active": True},
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
    )
    data = json.loads(origin.read_text(encoding="utf-8"))
    assert len(data["items"]) == 2
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_object_key_insert_relative_after_key_orders(tmp_path: Path) -> None:
    rel = "records/ordered.json"
    body = b'{"first":1,"third":3}\n'
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, body)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "second",
                            "value": 2,
                            "after_key": "first",
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
    )
    data = json.loads(origin.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["first", "second", "third"]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_batch_abort_on_second_invalid_operation(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    h0 = _sha(origin.read_bytes())
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        out = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/not_there"},
                        {"type": "replace", "json_pointer": "/items/0/id", "value": 9},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha(origin.read_bytes()) == h0


@pytest.mark.asyncio
async def test_json_replace_one_element_list_stays_array(tmp_path: Path) -> None:
    """Criterion E: one-element JSON list must remain a JSON array after commit."""
    rel = "records/single_array.json"
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, b'{"items":[]}\n')
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/items",
                            "value": [{"a": 1}],
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
    )
    body = origin.read_text(encoding="utf-8")
    assert '"items"' in body
    assert "[" in body
    data = json.loads(body)
    assert isinstance(data["items"], list)
    assert data["items"] == [{"a": 1}]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )


# A-1: RFC 6901 "/-" append sentinel must be accepted and append to the array.
@pytest.mark.asyncio
async def test_insert_array_element_via_rfc6901_append_sentinel(
    tmp_path: Path,
) -> None:
    """parent_json_pointer ending in '/-' must resolve the array and append."""
    rel = "records/sentinel.json"
    body = b'{"items":["a","b"]}\n'
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, body)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        result = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/items/-",
                            "value": "c",
                        }
                    ],
                }
            )
        )
    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    data = json.loads(origin.read_text(encoding="utf-8"))
    assert data["items"] == ["a", "b", "c"], data["items"]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )
