"""Tree-temp workspace path tests (T-006 A-002)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    SidecarWriteIntent,
    acquire_tree_temp_for_open,
    parse_source_bytes_to_roots,
)
from ai_editor.core.tree_temp.sidecar_payload import SidecarDocument, dumps_sidecar
from ai_editor.tree.sibling_convention import sibling_tree_path

_JSON_BYTES = b'{"a": 1}'


def _write_origin_sidecar(origin: Path, raw_source_bytes: bytes) -> Path:
    sha = hashlib.sha256(raw_source_bytes).hexdigest()
    roots = parse_source_bytes_to_roots("json", raw_source_bytes)
    sidecar_path = sibling_tree_path(origin.resolve())
    sidecar_path.write_text(
        dumps_sidecar(SidecarDocument(source_sha256=sha, root_nodes=roots)),
        encoding="utf-8",
    )
    return sidecar_path


def test_workspace_mode_reads_sidecar_beside_origin_writes_under_edit_subdir(
    tmp_path: Path,
) -> None:
    subtree = tmp_path / "sid" / "files" / "proj"
    origin = subtree / "data.json"
    origin.parent.mkdir(parents=True)
    origin.write_bytes(_JSON_BYTES)
    edit_root = subtree / "edit-uuid"
    edit_root.mkdir()

    read_sidecar = _write_origin_sidecar(origin, _JSON_BYTES)
    canonical = tmp_path / "canonical" / "data.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(_JSON_BYTES)

    result = acquire_tree_temp_for_open(
        project_root=tmp_path,
        source_abs=canonical,
        handler_id="json",
        raw_source_bytes=origin.read_bytes(),
        workspace_origin_path=origin,
        workspace_edit_root=edit_root,
    )

    assert result.sidecar_path == sibling_tree_path((edit_root / "data.json").resolve())
    assert result.roots
    assert result.sidecar_write_intent == SidecarWriteIntent.NONE
    assert read_sidecar.exists()
    assert not sibling_tree_path(canonical.resolve()).exists()


def test_workspace_mode_no_read_sidecar_creates_under_edit_subdir(
    tmp_path: Path,
) -> None:
    subtree = tmp_path / "sid" / "files" / "proj"
    origin = subtree / "data.json"
    origin.parent.mkdir(parents=True)
    origin.write_bytes(_JSON_BYTES)
    edit_root = subtree / "edit-uuid"
    edit_root.mkdir()
    canonical = tmp_path / "canonical" / "data.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(_JSON_BYTES)

    result = acquire_tree_temp_for_open(
        project_root=tmp_path,
        source_abs=canonical,
        handler_id="json",
        raw_source_bytes=origin.read_bytes(),
        workspace_origin_path=origin,
        workspace_edit_root=edit_root,
    )

    assert result.sidecar_path == sibling_tree_path((edit_root / "data.json").resolve())
    assert result.sidecar_write_intent == SidecarWriteIntent.CREATE
    assert not sibling_tree_path(canonical.resolve()).exists()


def test_legacy_mode_unchanged_sibling_path(tmp_path: Path) -> None:
    source = tmp_path / "proj" / "data.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(_JSON_BYTES)

    result = acquire_tree_temp_for_open(
        project_root=tmp_path,
        source_abs=source,
        handler_id="json",
        raw_source_bytes=_JSON_BYTES,
    )

    assert result.sidecar_path == sibling_tree_path(source.resolve())


def test_partial_workspace_kwargs_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be provided together"):
        acquire_tree_temp_for_open(
            project_root=tmp_path,
            source_abs=tmp_path / "x.json",
            handler_id="json",
            raw_source_bytes=b"{}",
            workspace_origin_path=tmp_path / "o.json",
        )
