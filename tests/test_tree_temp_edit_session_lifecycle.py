"""EditSession and tree-temp sidecar disk lifecycle via universal_file_* commands.

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
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    commit_write,
    materialize_tree_sidecar,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"


def _sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clear_json_trees() -> None:
    jtb._trees.clear()


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    _clear_json_trees()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    _clear_json_trees()


async def _open(
    tmp: Path, rel: str = "nested/demo.json", content: bytes = b'{"counter":7}\n'
) -> tuple[str, Path, Path, object]:
    reset_ca_session(DEFAULT_CA_SESSION_ID, rel)
    return await open_ca_file(
        tmp,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content,
    )


@pytest.mark.asyncio
async def test_roundtrip_commit_refreshes_sidecar_digest_matches_source(
    tmp_path: Path,
) -> None:
    rel = "nested/demo.json"
    sid, workspace, origin, upstream = await _open(tmp_path, rel)
    initial_sha = _sha_hex(origin.read_bytes())
    assert initial_sha

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        er = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "replace", "json_pointer": "/counter", "value": 88},
                    ],
                }
            )
        )
    assert isinstance(er, SuccessResult)

    commit_res = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    assert commit_res.data.get("uploaded") is True
    assert "88" in origin.read_text(encoding="utf-8")

    final_sha = _sha_hex(origin.read_bytes())
    sc = materialize_tree_sidecar(origin, file_path=rel)
    sections = parse_tree_file(sc.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == final_sha

    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        cr = await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )
    assert isinstance(cr, SuccessResult)


@pytest.mark.asyncio
async def test_close_without_write_after_edit_restores_original_hash(
    tmp_path: Path,
) -> None:
    rel = "nested/demo.json"
    sid, workspace, origin, upstream = await _open(tmp_path, rel)
    snap = origin.read_bytes()
    h0 = _sha_hex(snap)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {"type": "replace", "json_pointer": "/counter", "value": 99}
                    ],
                }
            )
        )

    assert origin.read_bytes() == snap

    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await close.execute(
            **close.validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid, "file_path": rel}
            )
        )

    assert _sha_hex(snap) == h0


@pytest.mark.asyncio
async def test_insert_into_object_using_after_key_maintains_order(
    tmp_path: Path,
) -> None:
    rel = "nested/order.json"
    body = b'{"alpha":true,"omega":false}\n'
    sid, workspace, origin, upstream = await _open(tmp_path, rel, body)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "between",
                            "value": 2,
                            "after_key": "alpha",
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
        file_path=rel,
    )

    data = json.loads(origin.read_text(encoding="utf-8"))

    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await close.execute(
            **close.validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid, "file_path": rel}
            )
        )
    assert list(data.keys()) == ["alpha", "between", "omega"]


@pytest.mark.asyncio
async def test_invalid_batch_returns_error_without_partial_mutation(
    tmp_path: Path,
) -> None:
    rel = "nested/batch.json"
    body = b'{"a":1}\n'
    sid, workspace, origin, upstream = await _open(tmp_path, rel, body)
    h0 = _sha_hex(origin.read_bytes())

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        out = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/nope"},
                        {"type": "replace", "json_pointer": "/a", "value": 2},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha_hex(origin.read_bytes()) == h0
