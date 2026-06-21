"""
Preview node_ref must resolve consistently in universal_file_edit (all formats).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.core.json_tree import tree_builder as jtb
from tests.fixtures.validation_passing_python import BAR_INSERT_LINES, MOD_WITH_FOO
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    commit_write,
    open_ca_file,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


async def _open_file(
    tmp: Path, rel: str, content: str
) -> tuple[str, Path, Path, object]:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    return await open_ca_file(
        tmp,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content.encode("utf-8"),
    )


async def _preview_blocks(
    workspace: Path,
    upstream: object,
    rel: str,
    *,
    session_id: str | None = None,
) -> list[dict]:
    cmd = UniversalFilePreviewCommand()
    params: dict[str, Any] = {"project_id": _PROJECT_UUID, "file_path": rel}
    if session_id is not None:
        params["session_id"] = session_id
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    blocks = list((res.data or {}).get("blocks") or [])
    if blocks:
        return blocks
    if session_id is None:
        return blocks
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(project_id=_PROJECT_UUID, file_path=rel)
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return list((res.data or {}).get("blocks") or [])


def _block_short_id(block: dict) -> str:
    ref = block.get("node_ref")
    if isinstance(ref, int):
        return str(ref)
    return str(ref).strip()


def _find_block_by_key_path(blocks: list[dict], key: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"key_path='{key}'" in attrs or f'key_path="{key}"' in attrs:
            return block
    raise AssertionError(f"no block for key {key!r} in {blocks!r}")


def _find_block_by_type(blocks: list[dict], node_type: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == node_type:
            return block
    raise AssertionError(f"no block with type {node_type!r} in {blocks!r}")


def _find_block_by_json_pointer(blocks: list[dict], pointer: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"json_pointer='{pointer}'" in attrs:
            return block
    raise AssertionError(f"no block for pointer {pointer!r} in {blocks!r}")


async def _commit(
    workspace: Path, upstream: object, sid: str, origin: Path, rel: str
) -> str:
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    text = origin.read_text(encoding="utf-8")
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await close.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
        )
    return text


@pytest.fixture(autouse=True)
def _reset_json_trees() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()


@pytest.mark.asyncio
async def test_json_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "data/doc.json"
    body = '{"items": [{"id": 1}], "meta": {"tag": "old"}}\n'
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    meta_block = _find_block_by_json_pointer(blocks, "/meta")
    meta_sid = _block_short_id(meta_block)

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
                            "type": "insert",
                            "target_node_id": meta_sid,
                            "position": "before",
                            "key": "note",
                            "value": "inserted",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    data = json.loads(text)
    keys = list(data.keys())
    assert keys.index("note") < keys.index("meta")
    assert data["note"] == "inserted"


@pytest.mark.asyncio
async def test_yaml_insert_by_preview_short_id_node_ref(tmp_path: Path) -> None:
    rel = "cfg/app.yaml"
    body = "alpha: 1\nbeta: 2\n"
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    beta_sid = _block_short_id(_find_block_by_key_path(blocks, "beta"))

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
                            "type": "insert",
                            "node_ref": beta_sid,
                            "position": "before",
                            "key": "middle",
                            "value": 99,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert text.index("middle:") < text.index("beta:")


@pytest.mark.asyncio
async def test_txt_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "notes/readme.txt"
    body = "First paragraph line.\n\nSecond paragraph line.\n"
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    second_sid = _block_short_id(
        next(b for b in blocks if int(_block_short_id(b)) >= 2)
    )

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
                            "type": "insert",
                            "target_node_id": second_sid,
                            "position": "before",
                            "content": "Inserted between paragraphs.\n",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert "Inserted between paragraphs." in text
    assert text.index("First paragraph") < text.index("Inserted between")
    assert text.index("Inserted between") < text.index("Second paragraph")


@pytest.mark.asyncio
async def test_jsonl_insert_by_preview_line_index_node_ref(tmp_path: Path) -> None:
    rel = "streams/events.jsonl"
    body = '{"event": "one"}\n{"event": "two"}\n'
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    line_ref = next(
        str(b["node_ref"]) for b in blocks if str(b.get("node_ref")) in ("1", 1)
    )

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
                            "type": "insert",
                            "node_ref": line_ref,
                            "position": "before",
                            "content": '{"event": "middle"}\n',
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[1] == '{"event": "middle"}'


@pytest.mark.asyncio
async def test_py_insert_by_preview_short_id_target_node_id(tmp_path: Path) -> None:
    rel = "src/mod.py"
    body = MOD_WITH_FOO
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    func_sid = _block_short_id(_find_block_by_type(blocks, "function"))

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
                            "type": "insert",
                            "target_node_id": func_sid,
                            "position": "before",
                            "code_lines": BAR_INSERT_LINES,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert text.index("def bar") < text.index("def foo")


@pytest.mark.asyncio
async def test_json_unknown_node_ref_not_silent_success(tmp_path: Path) -> None:
    rel = "data/x.json"
    sid, workspace, _origin, upstream = await _open_file(tmp_path, rel, '{"a": 1}\n')
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
                            "type": "insert",
                            "target_node_id": "99999",
                            "position": "before",
                            "key": "z",
                            "value": 0,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code in ("UNKNOWN_NODE_REF", "INVALID_OPERATION")
