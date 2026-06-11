"""YAML tree-temp preview sessions (universal_file_preview).

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
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    TreeTempOpenAcquisition,
    acquire_tree_temp_for_open,
)
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.core.tree_temp.tree_node import TreeNode
from ai_editor.core.yaml_tree import tree_builder as ytb
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
_PID_YAML = "1cedeced-1111-4222-8111-fedba5eba111"
_REL = "cluster/cfg/detail.yaml"
_BODY = b"""svc:
  env: prod
tag: go
# fin
"""
_PREVIEW_ACQUIRE_PATCH = (
    "ai_editor.commands.universal_file_preview_runtime.acquire_tree_temp_for_open"
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    ytb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    ytb._trees.clear()


def _mirror_origin_to_disk(tmp: Path, rel: str, origin: Path) -> Path:
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


def _pointer_to_key_path(pointer: str) -> str:
    norm = _normalize_pointer(pointer)
    if norm == "/":
        return ""
    return norm.strip("/").replace("/", ".")


def _uuid_for_pointer(*, source_path: Path, sidecar_path: Path, pointer: str) -> str:
    sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))
    handler = HandlerRegistry.default_registry().resolve(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(source_path, source_text)
    want = _pointer_to_key_path(pointer)
    target_short_id: int | None = None
    for node in nodes:
        kp = str(node.attributes.get("key_path", ""))
        if kp == want:
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
        handler_id="yaml",
        raw_source_bytes=source.read_bytes(),
    )


def _ids(blocks: list[dict[str, Any]]) -> set[str]:
    return {str(b[BLOCK_ID_KEY]) for b in blocks}


async def _open_write_commit_close(
    tmp: Path, rel: str, content: bytes
) -> tuple[Path, object, Path]:
    sid, workspace, origin, upstream = await open_ca_file(
        tmp,
        project_id=_PID_YAML,
        file_path=rel,
        content=content,
    )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PID_YAML,
        session_id=sid,
        file_path=rel,
    )
    materialize_tree_sidecar(origin, file_path=rel)
    source = _mirror_origin_to_disk(tmp, rel, origin)
    cl = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await cl.execute(
            **cl.validate_params({"project_id": _PID_YAML, "session_id": sid})
        )
    return workspace, upstream, source


async def _hydrate(tmp: Path) -> tuple[Path, object, Path]:
    return await _open_write_commit_close(tmp, _REL, _BODY)


async def _preview(
    workspace: Path, upstream: object, node_ref: str | None
) -> SuccessResult:
    cmd = UniversalFilePreviewCommand()
    raw: dict[str, Any] = {"project_id": _PID_YAML, "file_path": _REL}
    if node_ref is not None:
        raw["node_ref"] = node_ref
    params = raw
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult)
    return res


@pytest.mark.asyncio
async def test_yaml_scalar_node_ref_matches_container_preview_set(
    tmp_path: Path,
) -> None:
    workspace, upstream, _source = await _hydrate(tmp_path)
    acq = _preview_acquisition(tmp_path, _REL)
    su = _stable_id_in_forest(acq.roots, "/svc")
    eu = _stable_id_in_forest(acq.roots, "/svc/env")
    with patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq):
        a = await _preview(workspace, upstream, su)
        b = await _preview(workspace, upstream, eu)
    assert _ids(cast(list[dict[str, Any]], a.data["blocks"])) == _ids(
        cast(list[dict[str, Any]], b.data["blocks"])
    )


@pytest.mark.asyncio
async def test_yaml_root_scalar_matches_absent_node_ref(tmp_path: Path) -> None:
    rel = "solo.yaml"
    content = b"false\n"
    workspace, upstream, _source = await _open_write_commit_close(
        tmp_path, rel, content
    )
    sc = _sidecar_path(tmp_path, rel)
    assert sc.is_file()
    acq = _preview_acquisition(tmp_path, rel)
    rid = _stable_id_in_forest(acq.roots, "/")
    cmd = UniversalFilePreviewCommand()
    with (
        upstream_context(workspace=workspace, upstream=upstream),
        patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq),
    ):
        x = await cmd.execute(project_id=_PID_YAML, file_path=rel)
        y = await cmd.execute(
            project_id=_PID_YAML,
            file_path=rel,
            node_ref=rid,
        )
    assert isinstance(x, SuccessResult) and isinstance(y, SuccessResult)
    fx = cast(dict[str, Any], x.data["focus"])
    fy = cast(dict[str, Any], y.data["focus"])
    assert fx.get("node_kind") == "scalar"
    assert fy.get("type") == "tree_sidecar_focus"
    assert isinstance(fy.get("node_ref"), str) and len(str(fy.get("node_ref"))) >= 32


@pytest.mark.asyncio
async def test_yaml_sidecar_regenerates_stable_id_after_external_edit_with_sidecar_removed(
    tmp_path: Path,
) -> None:
    _workspace, _upstream, source = await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    old = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    edited = _BODY.replace(b"prod", b"staging")
    source.write_bytes(edited)
    sc.unlink(missing_ok=True)
    await _open_write_commit_close(tmp_path, _REL, edited)
    assert (
        _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
        != old
    )


@pytest.mark.asyncio
async def test_yaml_stable_id_stable_across_reopen_without_disk_change(
    tmp_path: Path,
) -> None:
    _workspace, _upstream, source = await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    disk_bytes = source.read_bytes()

    async def grab() -> str:
        sid, workspace, _origin, up = await open_ca_file(
            tmp_path,
            project_id=_PID_YAML,
            file_path=_REL,
            content=disk_bytes,
        )
        cl = UniversalFileCloseCommand()
        with upstream_context(workspace=workspace, upstream=up):
            await cl.execute(
                **cl.validate_params({"project_id": _PID_YAML, "session_id": sid})
            )
        return _uuid_for_pointer(
            source_path=source, sidecar_path=sc, pointer="/svc/env"
        )

    a = await grab()
    b = await grab()
    c = await grab()
    assert a == b == c


@pytest.mark.asyncio
async def test_yaml_unknown_node_ref_raises(tmp_path: Path) -> None:
    workspace, upstream, _source = await _hydrate(tmp_path)
    cmd = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(
            project_id=_PID_YAML,
            file_path=_REL,
            node_ref="00000000-0000-4000-8000-00000000ffff",
        )
    assert isinstance(res, ErrorResult)
