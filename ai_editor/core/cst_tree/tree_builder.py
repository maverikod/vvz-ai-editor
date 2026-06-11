"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import libcst as cst

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import PersistedNodeIds, strip_persisted_node_ids
from .node_stable_id import (
    logical_source_from_module,
    strip_inline_node_id_lines_from_source,
)
from .tree_builder_index import (
    _attach_disk_snapshot,
    _build_tree_index,
    _finalize_cst_tree,
    _strip_legacy_trailer_from_disk,
)

logger = logging.getLogger(__name__)


def _read_logical_py_source_sync_disk(py_path: Path) -> Tuple[str, PersistedNodeIds]:
    """Read Python source, strip persisted node-id markers, write disk if needed.

    Call before ``cst.parse_module`` so on-disk bytes match the logical source used
    for SHA snapshots (same policy as ``load_file_to_tree`` / save preflight).
    """
    raw = py_path.read_text(encoding="utf-8")
    logical, ids = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    if logical != raw:
        py_path.write_text(logical, encoding="utf-8")
    return logical, ids


def _on_disk_logical_matches_tree_snapshot(path: Path, tree: CSTTree) -> bool:
    """Return True when on-disk logical Python matches the tree's disk snapshot or module.

    Uses the same logical pipeline as ``load_file_to_tree`` / ``_attach_disk_snapshot``
    (strip markers, then UTF-8 SHA256 + length). When ``disk_source_sha256_hex`` is set,
    compares to that snapshot; otherwise compares on-disk logical bytes to
    ``tree.module.code`` (in-memory-only sessions).
    """
    if not path.is_file():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    logical, _ = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    logical_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(logical_bytes).hexdigest()
    length = len(logical_bytes)
    snap = tree.disk_source_sha256_hex
    if snap is not None:
        return digest == snap and length == tree.disk_source_length
    mod_bytes = logical_source_from_module(tree.module).encode("utf-8")
    return digest == hashlib.sha256(mod_bytes).hexdigest() and length == len(mod_bytes)


# In-memory storage for CST trees
_trees: dict[str, CSTTree] = {}


def load_file_to_tree(
    file_path: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Load file into CST tree and store in memory.

    Args:
        file_path: Path to Python file
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    is_py = path.suffix == ".py"
    is_py_tmp = path.suffix == ".tmp" and path.stem.endswith(".py")
    if not is_py and not is_py_tmp:
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    tree = CSTTree.create(str(path.resolve()), module)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    _trees[tree.tree_id] = tree
    return tree


def create_tree_from_code(
    file_path: str,
    source_code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    *,
    persist_sidecar: bool = False,
    register_in_memory: bool = True,
) -> CSTTree:
    """
    Create CST tree from source code string (without reading from file).

    This is useful for creating trees from code that doesn't exist on disk yet.

    Args:
        file_path: Path where file will be saved (used for tree metadata)
        source_code: Python source code string
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata
        persist_sidecar: When True and ``file_path`` exists on disk, write the sibling
            ``<source>.py.tree`` sidecar after indexing (used by DB sync / indexer).
        register_in_memory: When False, the tree is not stored in the global ``_trees`` map
            (used when the caller only needs a throwaway CST for one RPC).

    Returns:
        CSTTree with tree_id and metadata
    """
    logical_source, persisted_node_ids = strip_persisted_node_ids(source_code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    module = cst.parse_module(logical_source)

    tree = CSTTree.create(str(Path(file_path).resolve()), module)
    py_path = Path(file_path).resolve()
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=py_path,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=bool(persist_sidecar),
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0

    if register_in_memory:
        _trees[tree.tree_id] = tree
    return tree


def get_tree(tree_id: str) -> Optional[CSTTree]:
    """Return the in-memory CST tree, refreshing from disk when the file drifted.

    When ``disk_source_sha256_hex`` / ``disk_source_length`` were set at load time
    and the on-disk logical ``.py`` no longer matches that snapshot, the tree is
    rebuilt from disk (via :func:`reload_tree_from_file`) so ``stable_id`` / index
    state match the file. Trees without a disk snapshot (e.g. rollback-only
    in-memory state) are returned as-is.
    """
    tree = _trees.get(tree_id)
    if tree is None:
        return None
    tree.last_accessed_at = time.monotonic()
    path = Path(tree.file_path)
    snap = tree.disk_source_sha256_hex
    if snap is None or not path.is_file():
        return tree
    mod_snap = tree.module_source_sha256_hex
    if mod_snap is not None and mod_snap != snap:
        # Unsaved in-memory edits (e.g. universal_file_edit); do not reload from disk.
        return tree
    if _on_disk_logical_matches_tree_snapshot(path, tree):
        return tree
    reloaded = reload_tree_from_file(tree_id)
    return reloaded if reloaded is not None else tree


def remove_tree(tree_id: str) -> bool:
    """Remove tree from memory."""
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(
    tree_id: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> Optional[CSTTree]:
    """
    Reload tree from file, updating existing tree in memory.

    When the on-disk logical source still matches the tree's disk snapshot (and the
    caller uses default index parameters), returns the existing tree without
    reparsing or rebuilding the index. Otherwise reads the file, reparses, and
    runs a full index rebuild (``node_id_aliases`` are cleared on that path).

    The tree_id remains the same, so all references to the tree remain valid.

    Args:
        tree_id: Existing tree ID to update
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        Updated CSTTree or None if tree not found

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file is not a Python file
    """
    tree = _trees.get(tree_id)
    if not tree:
        return None

    # Read and parse file
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {tree.file_path}")

    default_index_params = (
        node_types is None and max_depth is None and include_children is True
    )
    if default_index_params and _on_disk_logical_matches_tree_snapshot(path, tree):
        tree.last_accessed_at = time.monotonic()
        return tree

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    previous_metadata_map = dict(tree.metadata_map)

    # Update tree in place
    tree.file_path = str(path.resolve())

    # Clear aliases before reload; sidecar or rebuild will repopulate if needed
    tree.node_id_aliases.clear()

    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    return tree


def rollback_tree_to_code(
    tree_id: str,
    code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    index_metadata_for_code: Optional[Dict[str, TreeNodeMetadata]] = None,
) -> bool:
    """
    Restore in-memory tree to the given source code (rollback after failed save).

    Replaces tree.module with parsed code and rebuilds index. Use when save
    fails after modify so the tree is reverted to pre-modify state.

    Disk snapshot fields (``disk_source_sha256_hex``, ``disk_source_length``) and
    ``module_source_sha256_hex`` are cleared: rollback reflects in-memory code only,
    not the file on disk, so save-side disk verification must not run against a stale
    snapshot until ``reload_tree_from_file`` / equivalent reload from disk.

    Args:
        tree_id: Tree ID to roll back
        code: Full module source code to restore
        node_types: Optional filter for index (same as load)
        max_depth: Optional max depth for index
        include_children: Whether to index children
        index_metadata_for_code: Optional snapshot of ``metadata_map`` that matches
            ``code`` (e.g. ``dict(tree.metadata_map)`` taken before ``modify_tree``).
            When provided, node_id stability is preserved across rollback; when omitted,
            the current in-memory map is used (legacy behavior).

    Returns:
        True if tree was found and rolled back, False if tree not found
    """
    tree = _trees.get(tree_id)
    if not tree:
        return False
    logical_source, persisted_node_ids = strip_persisted_node_ids(code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    # Must use metadata for the same source as ``code`` (typically pre-mutate
    # snapshot). Using the current tree.metadata_map after a failed or preview
    # mutate rebuilds UUIDs incorrectly and invalidates node_id stability.
    if index_metadata_for_code is not None:
        previous_metadata_map = index_metadata_for_code
    else:
        previous_metadata_map = dict(tree.metadata_map)
    module = cst.parse_module(logical_source)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=None,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=False,
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0
    # modify_tree updates module_source_sha256_hex; rollback must not leave a stale
    # digest that no longer matches tree.module.code (e.g. cst_modify_tree preview).
    tree.module_source_sha256_hex = None
    return True


CST_TREE_TTL_SECONDS: float = 900.0  # 15 minutes


async def _cst_tree_ttl_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [
            tid
            for tid, t in list(_trees.items())
            if (now - t.last_accessed_at) > CST_TREE_TTL_SECONDS
        ]
        for tid in expired:
            _trees.pop(tid, None)


def start_cst_tree_ttl_cleanup() -> None:
    asyncio.ensure_future(_cst_tree_ttl_cleanup_loop())
