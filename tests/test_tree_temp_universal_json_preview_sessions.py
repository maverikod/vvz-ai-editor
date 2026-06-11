"""JSON tree-temp preview sessions and stable id behaviour (universal_file_preview).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    TreeTempOpenAcquisition,
    acquire_tree_temp_for_open,
)
from ai_editor.core.json_tree import tree_builder as jtb
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.core.tree_temp.tree_node import TreeNode
from ai_editor.tree.handler_registry import HandlerRegistry
from ai_editor.tree.sibling_convention import sibling_tree_path
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    commit_write,
    materialize_tree_sidecar,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

BLOCK_ID_KEY = "node_ref"
_PID = "baddbadd-badd-4badd-badd-baddbaddbadd"
_REL = "cfg/detail.json"
_DOC = b'{"svc":{"env":"prod"},"tag":"go"}\n'
_PREVIEW_ACQUIRE_PATCH = (
    "ai_editor.commands.universal_file_preview_runtime.acquire_tree_temp_for_open"
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    jtb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    jtb._trees.clear()


def _mirror_origin_to_disk(tmp: Path, rel: str, origin: Path) -> Path:
    """Copy workspace origin (+ sidecar) to tmp for tree-temp acquisition helpers."""
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(origin.read_bytes())
    sc_origin = sibling_tree_path(origin.resolve())
    if sc_origin.is_file():
        sc_disk = sibling_tree_path(target.resolve())
        sc_disk.write_text(sc_origin.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _sidecar_path(tmp: Path, rel: str) -> Path:
    return sibling_tree_path((tmp / rel).resolve())


def _normalize_pointer(pointer: str) -> str:
    if pointer in ("", "/"):
        return "/"
    return pointer if pointer.startswith("/") else f"/{pointer}"


def _uuid_for_pointer(*, source_path: Path, sidecar_path: Path, pointer: str) -> str:
    sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))
    handler = HandlerRegistry.default_registry().resolve(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(source_path, source_text)
    want = _normalize_pointer(pointer)
    target_short_id: int | None = None
    for node in nodes:
        jp = str(node.attributes.get("json_pointer", ""))
        if jp == want or (want == "/" and jp in ("", "/")):
            target_short_id = int(node.short_id)
            break
    if target_short_id is None:
        raise KeyError(want)
    for entry in sections.map.entries:
        if entry.short_id == target_short_id:
            return entry.uuid
    raise KeyError(want)


def _stable_id_in_forest(roots: list[TreeNode], pointer: str) -> str:
    norm = _normalize_pointer(pointer)
    if norm == "/":
        assert len(roots) == 1
        return str(roots[0].stable_id)
    node = roots[0]
    for raw in norm.strip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if node.type == "object":
            children = node.children or []
            match = next((c for c in children if c.key == part), None)
            if match is None:
                raise KeyError(part)
            node = match
        elif node.type == "array":
            children = node.children or []
            node = children[int(part)]
        else:
            raise KeyError(pointer)
    return str(node.stable_id)


def _preview_acquisition(tmp: Path, rel: str) -> TreeTempOpenAcquisition:
    source = (tmp / rel).resolve()
    return acquire_tree_temp_for_open(
        project_root=tmp.resolve(),
        source_abs=source,
        handler_id="json",
        raw_source_bytes=source.read_bytes(),
    )


def _ids(blocks: list[dict[str, Any]]) -> set[str]:
    return {str(b[BLOCK_ID_KEY]) for b in blocks}


async def _open_write_commit_close(
    tmp: Path, rel: str, content: bytes
) -> tuple[Path, object, Path]:
    sid, workspace, origin, upstream = await open_ca_file(
        tmp,
        project_id=_PID,
        file_path=rel,
        content=content,
    )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PID,
        session_id=sid,
        file_path=rel,
    )
    materialize_tree_sidecar(origin, file_path=rel)
    source = _mirror_origin_to_disk(tmp, rel, origin)
    cl = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await cl.execute(**cl.validate_params({"project_id": _PID, "session_id": sid}))
    return workspace, upstream, source


async def _hydrate(tmp: Path) -> tuple[Path, object, Path]:
    return await _open_write_commit_close(tmp, _REL, _DOC)


async def _preview(
    workspace: Path, upstream: object, node_ref: str | None
) -> SuccessResult:
    cmd = UniversalFilePreviewCommand()
    params: dict[str, Any] = {"project_id": _PID, "file_path": _REL}
    if node_ref is not None:
        params["node_ref"] = node_ref
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult)
    return res


@pytest.mark.asyncio
async def test_scalar_stable_id_resolves_container_children_matching_parent_preview(
    tmp_path: Path,
) -> None:
    workspace, upstream, _source = await _hydrate(tmp_path)
    acq = _preview_acquisition(tmp_path, _REL)
    svc_uuid = _stable_id_in_forest(acq.roots, "/svc")
    scalar_uuid = _stable_id_in_forest(acq.roots, "/svc/env")

    with patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq):
        pr_par = await _preview(workspace, upstream, svc_uuid)
        pr_sc = await _preview(workspace, upstream, scalar_uuid)
    b1 = cast(list[dict[str, Any]], (pr_par.data or {}).get("blocks") or [])
    b2 = cast(list[dict[str, Any]], (pr_sc.data or {}).get("blocks") or [])
    p_set = _ids(b1)
    s_set = _ids(b2)
    assert p_set == s_set
    assert len(p_set) > 0


@pytest.mark.asyncio
async def test_root_scalar_json_preview_equivalent_without_ref(tmp_path: Path) -> None:
    rel = "solo.json"
    content = b"false\n"
    workspace, upstream, _source = await _open_write_commit_close(
        tmp_path, rel, content
    )
    sc = _sidecar_path(tmp_path, rel)
    assert sc.is_file()
    acq = _preview_acquisition(tmp_path, rel)
    root_uuid = _stable_id_in_forest(acq.roots, "/")
    cmd = UniversalFilePreviewCommand()
    with (
        upstream_context(workspace=workspace, upstream=upstream),
        patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq),
    ):
        a = await cmd.execute(project_id=_PID, file_path=rel)
        b = await cmd.execute(
            project_id=_PID,
            file_path=rel,
            node_ref=root_uuid,
        )
    assert isinstance(a, SuccessResult) and isinstance(b, SuccessResult)
    fa = cast(dict[str, Any], a.data["focus"])
    fb = cast(dict[str, Any], b.data["focus"])
    assert fa.get("node_kind") == "scalar"
    assert fb.get("type") == "tree_sidecar_focus"
    assert isinstance(fb.get("node_ref"), str) and len(str(fb.get("node_ref"))) >= 32


@pytest.mark.asyncio
async def test_rescan_after_external_edit_and_removed_sidecar_generates_new_uuid(
    tmp_path: Path,
) -> None:
    _workspace, _upstream, source = await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    old = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    edited = _DOC.replace(b"prod", b"staging")
    source.write_bytes(edited)
    sc.unlink(missing_ok=True)
    await _open_write_commit_close(tmp_path, _REL, edited)
    new_u = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    assert new_u != old


@pytest.mark.asyncio
async def test_stable_id_persists_across_sessions_without_disk_change(
    tmp_path: Path,
) -> None:
    _workspace, upstream, source = await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    disk_bytes = source.read_bytes()

    async def cycle() -> str:
        sid, workspace, _origin, up = await open_ca_file(
            tmp_path,
            project_id=_PID,
            file_path=_REL,
            content=disk_bytes,
        )
        cl = UniversalFileCloseCommand()
        with upstream_context(workspace=workspace, upstream=up):
            await cl.execute(
                **cl.validate_params({"project_id": _PID, "session_id": sid})
            )
        return _uuid_for_pointer(
            source_path=source, sidecar_path=sc, pointer="/svc/env"
        )

    u1 = await cycle()
    u2 = await cycle()
    u3 = await cycle()
    assert u1 == u2 == u3
    _ = upstream


@pytest.mark.asyncio
async def test_unknown_node_ref_errors(tmp_path: Path) -> None:
    workspace, upstream, _source = await _hydrate(tmp_path)
    cmd = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(
            project_id=_PID,
            file_path=_REL,
            node_ref="00000000-0000-4000-8000-00000000ffff",
        )
    assert isinstance(res, ErrorResult)
    assert res.code
    assert "UNKNOWN" in str(res.code).upper() or "INPUT" in str(res.code).upper()
