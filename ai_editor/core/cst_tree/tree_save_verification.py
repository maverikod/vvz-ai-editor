"""
Pure verification helpers before/after CST tree save (snapshot, replay, read-back).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import hashlib

from collections import defaultdict

from dataclasses import replace

from pathlib import Path

from typing import (
    DefaultDict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)


from .models import ROOT_NODE_ID_SENTINEL, CSTTree, TreeNodeMetadata, TreeOperation

from .node_id_markers import build_exact_node_key

from .node_stable_id import logical_source_from_module

from .tree_builder import create_tree_from_code, get_tree, remove_tree

from .tree_modifier import modify_tree


FILE_CHANGED_SINCE_LOAD = "FILE_CHANGED_SINCE_LOAD"

CST_REPLAY_MISMATCH = "CST_REPLAY_MISMATCH"

WRITE_VERIFY_FAILED = "WRITE_VERIFY_FAILED"
TREE_MODULE_CORRUPT = "TREE_MODULE_CORRUPT"


class SaveVerificationError(Exception):
    """Raised when a save-time verification invariant fails."""

    def __init__(
        self, *, code: str, details: Mapping[str, object] | None = None
    ) -> None:
        self.code = code
        self.details: dict[str, object] = dict(details) if details is not None else {}
        super().__init__(code)


def _resolve_meta_for_replay_remap(
    node_id: str,
    ref_tree: CSTTree,
    id_lookup_tree: Optional[CSTTree],
) -> Optional[TreeNodeMetadata]:
    if not node_id or node_id == ROOT_NODE_ID_SENTINEL:
        return None
    meta = ref_tree.metadata_map.get(node_id)
    if meta is not None:
        return meta
    if id_lookup_tree is not None:
        return id_lookup_tree.metadata_map.get(node_id)
    return None


def _replay_node_id_for_operation_id(
    node_id: str,
    ref_tree: CSTTree,
    replay_tree: CSTTree,
    id_lookup_tree: Optional[CSTTree],
    exact_to_replay_id: dict[Tuple[int, int, int, int, str], str],
    loose_to_replay_ids: dict[Tuple[int, int, str], List[str]],
) -> str:
    if not node_id or node_id == ROOT_NODE_ID_SENTINEL:
        return node_id
    if node_id in replay_tree.metadata_map:
        return node_id
    meta = _resolve_meta_for_replay_remap(node_id, ref_tree, id_lookup_tree)
    if meta is None:
        return node_id
    exact_key = build_exact_node_key(
        meta.start_line,
        meta.start_col,
        meta.end_line,
        meta.end_col,
        meta.type,
    )
    mapped = exact_to_replay_id.get(exact_key)
    if mapped is not None:
        return mapped
    loose_key = (meta.start_line, meta.start_col, meta.type)
    cands = loose_to_replay_ids.get(loose_key)
    if not cands:
        return node_id
    if len(cands) == 1:
        return cands[0]
    best: Optional[str] = None
    best_score: Optional[Tuple[int, int]] = None
    for rid in cands:
        rm = replay_tree.metadata_map.get(rid)
        if rm is None:
            continue
        score = (
            abs(rm.end_line - meta.end_line),
            abs(rm.end_col - meta.end_col),
        )
        if best_score is None or score < best_score:
            best_score = score
            best = rid
    return best if best is not None else node_id


def _remap_ops_to_replay_tree(
    ops: Sequence[TreeOperation],
    ref_tree: CSTTree,
    replay_tree: CSTTree,
    id_lookup_tree: Optional[CSTTree],
) -> List[TreeOperation]:
    exact_to_replay_id: dict[Tuple[int, int, int, int, str], str] = {}
    loose_to_replay_ids: DefaultDict[Tuple[int, int, str], List[str]] = defaultdict(
        list
    )
    for rid, rmeta in replay_tree.metadata_map.items():
        exact_key = build_exact_node_key(
            rmeta.start_line,
            rmeta.start_col,
            rmeta.end_line,
            rmeta.end_col,
            rmeta.type,
        )
        exact_to_replay_id[exact_key] = rid
        loose_to_replay_ids[(rmeta.start_line, rmeta.start_col, rmeta.type)].append(rid)

    def _remap_one(nid: Optional[str]) -> Optional[str]:
        if not nid:
            return nid
        return _replay_node_id_for_operation_id(
            nid,
            ref_tree,
            replay_tree,
            id_lookup_tree,
            exact_to_replay_id,
            loose_to_replay_ids,
        )

    out: List[TreeOperation] = []
    for op in ops:
        out.append(
            replace(
                op,
                node_id=_remap_one(op.node_id) or "",
                parent_node_id=_remap_one(op.parent_node_id),
                target_node_id=_remap_one(op.target_node_id),
                start_node_id=_remap_one(op.start_node_id),
                end_node_id=_remap_one(op.end_node_id),
            )
        )
    return out


def _replay_operations_produce_code_at_path(
    original_source: str,
    tree_operations: Sequence[TreeOperation],
    replay_file_path: str,
    *,
    id_lookup_tree: Optional[CSTTree] = None,
) -> str:
    ref_tree = create_tree_from_code(
        replay_file_path,
        original_source,
        persist_sidecar=False,
        register_in_memory=False,
    )
    replay_tree = create_tree_from_code(
        replay_file_path,
        original_source,
        persist_sidecar=False,
    )
    new_id = replay_tree.tree_id
    remapped = _remap_ops_to_replay_tree(
        tree_operations, ref_tree, replay_tree, id_lookup_tree
    )
    try:
        modify_tree(new_id, remapped)
        final = get_tree(new_id)
        if final is None:
            raise SaveVerificationError(
                code=CST_REPLAY_MISMATCH,
                details={
                    "reason": "replay_tree_missing_after_modify",
                    "tree_id": new_id,
                    "replay_file_path": replay_file_path,
                },
            )
        return cast(str, final.module.code)
    finally:
        remove_tree(new_id)


def disk_matches_tree_snapshot(target_path: Path, tree: CSTTree) -> bool:
    """
    Compare current disk UTF-8 bytes (sha256 + length) with the snapshot on ``tree``.

    Returns False when the snapshot is absent, when the path is unreadable, or when
    the digest/size do not match.
    """
    snapshot_hex = tree.disk_source_sha256_hex
    if snapshot_hex is None:
        return False
    path = Path(target_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return bool(digest == snapshot_hex and len(raw) == tree.disk_source_length)


def assert_disk_matches_tree_snapshot(target_path: Path, tree: CSTTree) -> None:
    """Raise SaveVerificationError if the file on disk no longer matches the load snapshot."""
    if disk_matches_tree_snapshot(target_path, tree):
        return
    path = Path(target_path)
    snapshot_hex = tree.disk_source_sha256_hex
    snapshot_len = tree.disk_source_length
    disk_hex: str | None = None
    disk_len: int | None = None
    read_error: str | None = None
    try:
        text = path.read_text(encoding="utf-8")
        raw = text.encode("utf-8")
        disk_hex = hashlib.sha256(raw).hexdigest()
        disk_len = len(raw)
    except OSError as exc:
        read_error = str(exc)
    details: MutableMapping[str, object] = {
        "target_path": str(path),
        "snapshot_sha256_hex": snapshot_hex,
        "snapshot_length": snapshot_len,
    }
    if disk_hex is not None:
        details["disk_sha256_hex"] = disk_hex
    if disk_len is not None:
        details["disk_length"] = disk_len
    if read_error is not None:
        details["read_error"] = read_error
    raise SaveVerificationError(code=FILE_CHANGED_SINCE_LOAD, details=dict(details))


def replay_operations_produce_code(
    original_source: str,
    tree_operations: Sequence[TreeOperation],
) -> str:
    """Parse ``original_source``, apply ``tree_operations`` on a fresh tree; return serialized code."""
    stub = str(Path("_cst_save_verification_replay_stub.py").resolve())
    return _replay_operations_produce_code_at_path(
        original_source, tree_operations, stub, id_lookup_tree=None
    )


def assert_replay_matches(
    *,
    original_source: str,
    target_path: Path,
    tree: CSTTree,
    tree_operations: Sequence[TreeOperation],
    id_lookup_tree: Optional[CSTTree] = None,
) -> None:
    """
    Replay the same edits on ``original_source`` and require the result equals ``tree.module.code``.
    Removes the temporary replay tree from ``_trees`` via try/finally.

    ``id_lookup_tree`` resolves operation ``node_id`` values that are absent from the fresh
    replay parse (and from ``tree`` after destructive replaces). When omitted, ``tree`` is used.
    """
    lookup = id_lookup_tree if id_lookup_tree is not None else tree
    replayed = _replay_operations_produce_code_at_path(
        original_source,
        tree_operations,
        str(target_path),
        id_lookup_tree=lookup,
    )
    working = logical_source_from_module(tree.module)
    if replayed == working:
        return
    raise SaveVerificationError(
        code=CST_REPLAY_MISMATCH,
        details={
            "target_path": str(Path(target_path)),
            "replay_length": len(replayed),
            "working_length": len(working),
        },
    )


def assert_file_bytes_match(*, target_path: Path, expected: str) -> None:
    """After atomic replace: require ``read_text`` matches ``expected`` (UTF-8, strict equality)."""
    actual = Path(target_path).read_text(encoding="utf-8")
    if actual == expected:
        return
    raise SaveVerificationError(
        code=WRITE_VERIFY_FAILED,
        details={
            "target_path": str(Path(target_path)),
            "expected_length": len(expected),
            "actual_length": len(actual),
        },
    )


def assert_tree_module_integrity(tree: CSTTree) -> None:
    """Raise SaveVerificationError if logical module source SHA256 doesn't match snapshot.

    Compares canonical source (no legacy inline ``# @node-id`` lines). ``stable_id``
    lives in ``metadata_map`` / sidecar and is not part of this checksum.
    """
    expected_hex = tree.module_source_sha256_hex
    if expected_hex is None:
        return
    actual_code = logical_source_from_module(tree.module)
    actual_hex = hashlib.sha256(actual_code.encode("utf-8")).hexdigest()
    if actual_hex == expected_hex:
        return
    raise SaveVerificationError(
        code=TREE_MODULE_CORRUPT,
        details={
            "tree_id": tree.tree_id,
            "file_path": tree.file_path,
            "expected_sha256": expected_hex,
            "actual_sha256": actual_hex,
            "expected_lines": actual_code.count("\n"),
            "actual_lines": actual_code.count("\n"),
        },
    )
