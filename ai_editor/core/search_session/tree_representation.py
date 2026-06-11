"""
TreeRepresentation validation lifecycle for paginated search sessions.

Integration layer over existing tree-temp and CST sidecar storage. Full tree
parsers are delegated to indexer hooks; this module resolves sidecar paths,
classifies formats, and validates checksum freshness before structural search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
import yaml
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, cast

from ai_editor.core.cst_tree.tree_sidecar import read_sidecar_payload
from ai_editor.core.structure_extraction.format_registry import (
    JSON_SUFFIX,
    MD_SUFFIXES,
    PY_SUFFIXES,
    TEXT_PLAIN_SUFFIXES,
    YAML_SUFFIXES,
    suffix_for_path,
)
from ai_editor.core.tree_temp.sidecar_payload import (
    SidecarParseError,
    loads_sidecar,
)
from ai_editor.tree.sibling_convention import sibling_tree_path


class TreeFormatKind(str, Enum):
    """Supported TreeRepresentation storage formats."""

    json = "json"
    yaml = "yaml"
    python_cst = "python_cst"
    markdown = "markdown"
    text = "text"


class TreeValidityState(str, Enum):
    """Whether validate_or_recreate_tree returned an existing valid sidecar or rebuilt it."""

    reused = "reused"
    recreated = "recreated"


@dataclass(frozen=True)
class TreeRepresentationRef:
    """Validated on-disk tree sidecar reference for one project file."""

    file_path: str
    sidecar_path: Path
    content_checksum: str
    root_stable_id: Optional[str]


def classify_tree_format(file_path: str) -> TreeFormatKind:
    """Map a project-relative file path to its TreeRepresentation format."""
    suffix = suffix_for_path(file_path)
    if suffix == JSON_SUFFIX:
        return TreeFormatKind.json
    if suffix in YAML_SUFFIXES:
        return TreeFormatKind.yaml
    if suffix in PY_SUFFIXES:
        return TreeFormatKind.python_cst
    if suffix in MD_SUFFIXES:
        return TreeFormatKind.markdown
    if suffix in TEXT_PLAIN_SUFFIXES:
        return TreeFormatKind.text
    raise ValueError(f"unsupported tree format for path: {file_path}")


def sidecar_path_for(file_path: str, project_root: Path) -> Path:
    """Return the absolute sidecar path for *file_path* under *project_root*.

    All formats use the sibling convention ``<source>.tree`` next to the source
    file.
    """
    source_abs = (project_root / Path(file_path)).resolve()
    return sibling_tree_path(source_abs)


def _compute_file_sha256_hex(source_abs: Path) -> str:
    digest = hashlib.sha256()
    with source_abs.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_tree_temp_root_stable_id(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = loads_sidecar(text)
    except (SidecarParseError, ValueError):
        return None
    if not doc.root_nodes:
        return None
    return cast(str, doc.root_nodes[0].stable_id)


def _read_tree_temp_digest(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = loads_sidecar(text)
    except (SidecarParseError, ValueError):
        return None
    return cast(str, doc.source_sha256)


def _read_three_section_digest_and_root(
    sidecar_path: Path,
) -> tuple[Optional[str], Optional[str]]:
    """Read CHECKSUMS/MAP from unified three-section ``.tree`` sidecar."""
    try:
        from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file

        text = sidecar_path.read_text(encoding="utf-8")
        sections = parse_tree_file(text)
    except OSError:
        return None, None
    except Exception:
        return None, None
    digest = sections.checksums.get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return None, None
    root_stable_id: Optional[str] = None
    if sections.map.entries:
        root_stable_id = str(sections.map.entries[0].short_id)
    return digest.lower(), root_stable_id


def _read_cst_digest_and_root(
    source_abs: Path, sidecar_path: Path
) -> tuple[Optional[str], Optional[str]]:
    payload = read_sidecar_payload(source_abs)
    if payload is not None:
        digest = payload.get("source_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            return None, None
        root_id = payload.get("root_node_id")
        root_stable_id = root_id if isinstance(root_id, str) and root_id else None
        return digest.lower(), root_stable_id
    if sidecar_path.is_file():
        return _read_three_section_digest_and_root(sidecar_path)
    return None, None


def _read_adjacent_sidecar_digest(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    digest = payload.get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return None
    return digest.lower()


def _read_adjacent_root_stable_id(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    root_id = payload.get("root_stable_id")
    if isinstance(root_id, str) and root_id:
        return root_id
    root_nodes = payload.get("root")
    if isinstance(root_nodes, list) and root_nodes:
        first = root_nodes[0]
        if isinstance(first, dict):
            stable_id = first.get("stable_id")
            if isinstance(stable_id, str) and stable_id:
                return stable_id
    return None


def _read_sidecar_state(
    *,
    kind: TreeFormatKind,
    source_abs: Path,
    sidecar_path: Path,
) -> tuple[Optional[str], Optional[str]]:
    if not sidecar_path.is_file():
        return None, None
    if kind == TreeFormatKind.python_cst:
        return _read_cst_digest_and_root(source_abs, sidecar_path)
    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        digest = _read_tree_temp_digest(sidecar_path)
        root_id = _read_tree_temp_root_stable_id(sidecar_path)
        return digest, root_id
    digest = _read_adjacent_sidecar_digest(sidecar_path)
    root_id = _read_adjacent_root_stable_id(sidecar_path)
    return digest, root_id


def _recreate_tree_for_format(
    *,
    kind: TreeFormatKind,
    project_root: Path,
    file_path: str,
    source_abs: Path,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild a missing or stale sidecar via existing indexer tree builders."""
    import os
    import yaml as _yaml

    source_text = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, project_root)
    if kind == TreeFormatKind.python_cst:
        from ai_editor.core.cst_tree.tree_builder import create_tree_from_code

        create_tree_from_code(str(source_abs), source_text, persist_sidecar=True)
        digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )
    if kind == TreeFormatKind.json:
        from ai_editor.core.json_tree.tree_builder import build_tree_from_data
        from ai_editor.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )

        data = json.loads(source_text)
        tree = build_tree_from_data(data, source_path=str(source_abs))
        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )
    if kind == TreeFormatKind.yaml:
        from ai_editor.core.yaml_tree.tree_builder import build_yaml_tree_from_data
        from ai_editor.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )

        data = _yaml.safe_load(source_text)
        tree = build_yaml_tree_from_data(data, source_path=str(source_abs))
        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )
    # markdown or text — sibling .tree
    from ai_editor.core.structure_extraction.extractor import extract_structure

    extract_structure(str(source_abs), ensure_persisted_tree=True)
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_tree(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """Validate sidecar checksum against source SHA-256 or recreate when stale.

    Returns (ref, reused) when fresh; (ref, recreated) after rebuild.
    Raises FileNotFoundError when source absent.
    """
    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content_checksum = _compute_file_sha256_hex(source_abs)
    sidecar_path = sidecar_path_for(file_path, root)
    if not force:
        sidecar_digest, root_stable_id = _read_sidecar_state(
            kind=kind,
            source_abs=source_abs,
            sidecar_path=sidecar_path,
        )
        if sidecar_digest is not None and sidecar_digest == content_checksum:
            return (
                TreeRepresentationRef(
                    file_path=file_path,
                    sidecar_path=sidecar_path,
                    content_checksum=content_checksum,
                    root_stable_id=root_stable_id,
                ),
                TreeValidityState.reused,
            )
    ref = _recreate_tree_for_format(
        kind=kind,
        project_root=root,
        file_path=file_path,
        source_abs=source_abs,
        content_checksum=content_checksum,
    )
    return ref, TreeValidityState.recreated


__all__ = [
    "TreeFormatKind",
    "TreeValidityState",
    "TreeRepresentationRef",
    "classify_tree_format",
    "sidecar_path_for",
    "validate_or_recreate_tree",
]
