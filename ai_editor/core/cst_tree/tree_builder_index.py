"""
CST tree indexing helpers — sidecar finalize and tree index build.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_key_to_id_from_metadata,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from .node_type_utils import (
    decorator_stable_id,
    get_node_kind,
    get_node_name,
    get_node_qualname,
)
from .node_stable_id import (
    get_stable_id as _get_stable_id_from_node,
    logical_source_from_module,
    strip_inline_node_id_lines_from_source,
)
from .tree_stable_data import (
    _STATEMENT_STABLE_TYPES,
    build_statement_stable_key,
    normalized_source_span,
)
from .tree_sidecar import (
    aliases_from_payload,
    metadata_map_from_payload,
    persisted_node_ids_from_payload,
    read_sidecar_payload,
    sidecar_matches_built_tree,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)

logger = logging.getLogger(__name__)


def _attach_disk_snapshot(tree: CSTTree, source: str) -> None:
    """Record SHA256 + length of logical source (no ``# @node-id`` markers) on tree."""
    logical = strip_inline_node_id_lines_from_source(source)
    source_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(source_bytes).hexdigest()
    tree.disk_source_sha256_hex = digest
    tree.disk_source_length = len(source_bytes)
    tree.module_source_sha256_hex = digest


def _strip_legacy_trailer_from_disk(py_path: Path, logical_source: str) -> None:
    """Atomically overwrite py_path with logical_source if the file still contains
    a legacy # cst-node-ids block (raw != logical). Safe: writes to .tmp then os.replace.
    """
    try:
        tmp_path = py_path.with_suffix(".py.tmp")
        tmp_path.write_text(logical_source, encoding="utf-8")
        os.replace(str(tmp_path), str(py_path))
        logger.info("Stripped legacy cst-node-ids trailer from %s", py_path)
    except OSError as exc:
        logger.warning("Could not strip legacy trailer from %s: %s", py_path, exc)


def _finalize_cst_tree(
    tree: CSTTree,
    module: cst.Module,
    logical_source: str,
    *,
    py_path: Optional[Path],
    raw_disk_source: Optional[str],
    node_types: Optional[List[str]],
    max_depth: Optional[int],
    include_children: bool,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]],
    legacy_persisted: PersistedNodeIds,
    write_sidecar: bool,
    previous_module: Optional[cst.Module] = None,
) -> None:
    """
    Parse-time CST index: try the sibling ``<source>.py.tree`` sidecar when SHA matches; else full
    ``_build_tree_index`` (legacy marker path map + optional previous metadata).
    """
    tree.module = module

    if py_path is not None:
        payload = read_sidecar_payload(py_path)
        if payload is not None and verify_sidecar_against_source(
            logical_source, payload
        ):
            order_raw = payload.get("metadata_node_order")
            meta_order = (
                [str(x) for x in order_raw] if isinstance(order_raw, list) else None
            )
            prev_side = metadata_map_from_payload(
                payload.get("metadata_map", {}),
                meta_order,
            )
            persisted_side = persisted_node_ids_from_payload(payload)
            if prev_side and persisted_side:
                tree.node_map.clear()
                tree.metadata_map.clear()
                tree.parent_map.clear()
                tree.node_id_aliases.clear()
                _build_tree_index(
                    tree,
                    node_types=node_types,
                    max_depth=max_depth,
                    include_children=include_children,
                    previous_metadata_map=prev_side,
                    persisted_node_ids=persisted_side,
                    # NOTE: no previous_module here -- prev_side comes from the
                    # sidecar payload, already content-verified against the
                    # CURRENT logical_source (verify_sidecar_against_source
                    # above), not from the caller's previous_module snapshot
                    # (which may describe a different prior state, e.g. the
                    # in-memory tree before an out-of-band on-disk edit).
                    # Passing previous_module here would compare unrelated
                    # content and wrongly reject legitimate sidecar-based id
                    # reuse.
                )
                if sidecar_matches_built_tree(tree, payload):
                    tree.node_id_aliases = aliases_from_payload(payload)
                    if raw_disk_source is not None:
                        # SHA must match logical source (no inline/legacy markers)
                        _attach_disk_snapshot(tree, logical_source)
                        # Strip inline/legacy markers from disk unconditionally
                        if raw_disk_source != logical_source and py_path is not None:
                            _strip_legacy_trailer_from_disk(py_path, logical_source)
                    return
                tree.module = cst.parse_module(logical_source)

    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    if previous_metadata_map is None:
        tree.node_id_aliases.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=legacy_persisted or None,
        previous_module=previous_module,
    )
    if raw_disk_source is not None:
        # SHA must match logical source (no inline/legacy markers)
        _attach_disk_snapshot(tree, logical_source)
        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)
        if raw_disk_source != logical_source and py_path is not None:
            _strip_legacy_trailer_from_disk(py_path, logical_source)
    if write_sidecar and py_path is not None:
        try:
            write_sidecar_atomic(py_path, tree)
        except OSError as exc:
            logger.warning("Could not write CST sidecar for %s: %s", py_path, exc)


def _deterministic_fresh_node_id(
    file_path: str,
    node_type: str,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
    content_text: str,
    marker_path: str,
) -> str:
    """Deterministic fallback identity for a node with no persisted/carried id.

    Two independent rebuilds of byte-identical source (e.g. a search-triggered
    rebuild and a later, unrelated edit-triggered rebuild of the same session
    file, each falling back to ``previous_metadata_map=None`` because the other
    tree instance/tree_id is no longer resolvable) must mint the SAME
    node_id/stable_id for the same node; otherwise an identifier captured from
    one rebuild is rejected (``STALE_NODE_ID``) by code operating on the other.
    ``uuid.uuid4()`` is random per call and cannot provide that.

    ``content_text`` (normalized source at this node's span) MUST be part of
    the key, not just position: this same fallback also fires right after the
    content-equivalence gate above rejects an ``exact_key_to_id`` reuse
    candidate (bug 086a8f6c -- a structural edit shifted a different node onto
    that exact coordinate span). A position-only hash would then reproduce the
    very same coordinate collision it was minted to avoid, deterministically
    recreating the OLD occupant's id for the NEW occupant of that span.
    Folding in the content breaks that tie while keeping two independent
    rebuilds of byte-identical (position AND content) source in agreement.

    ``marker_path`` (the traversal path from the module root, same shape as
    the persisted-marker path key) MUST also be part of the key: two distinct
    zero-width nodes (e.g. two separate empty ``SimpleWhitespace`` slots in a
    ``def f():`` header) can share the exact same
    (type, start, end) coordinates *and* the same whole-line normalized text,
    yet are different children of different fields and must not collapse onto
    one node_id. The traversal path is unique per node within a single parse
    and, for byte-identical source, is itself reproduced identically by an
    independent rebuild (same AST shape -> same child-index path), so adding
    it does not weaken the cross-rebuild determinism this function exists for.

    The digest is re-stamped with UUID version/variant bits (``version=4``)
    so the result is byte-for-byte indistinguishable, format-wise, from a
    genuine random UUID4 (passes ``_is_valid_uuid4`` used to validate mutation
    targets elsewhere in the edit pipeline) while remaining fully
    deterministic for a given (file_path, node_type, position, content,
    marker_path) tuple.
    """
    key = "|".join(
        [
            file_path,
            node_type,
            str(start_line),
            str(start_col),
            str(end_line),
            str(end_col),
            content_text,
            marker_path,
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
    persisted_node_ids: Optional[PersistedNodeIds] = None,
    pinned_node_id: Optional[str] = None,
    obj_to_stable: Optional[Dict[Any, str]] = None,
    previous_module: Optional[cst.Module] = None,
) -> None:
    """
    Build node index and metadata for tree.

    ``stable_id`` lives in ``TreeNodeMetadata`` (sidecar JSON). After mutation,
    it is carried over via semantic keys (qualname, statement text), not coordinates.

    ``previous_module`` is the pre-mutation module snapshot (when available):
    it gates ``node_id`` reuse from ``exact_key_to_id`` on content equivalence
    (same normalized text at that position in the prior source), so a
    structural edit that shifts line numbers (e.g. deleting the first of
    several imports) cannot make an unrelated statement inherit another
    statement's ``node_id`` by coordinate coincidence alone (bug 086a8f6c).
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    exact_key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    exact_key_to_content: Dict[Tuple[int, int, int, int, str], str] = {}
    if previous_metadata_map:
        for key, node_id in build_exact_key_to_id_from_metadata(
            previous_metadata_map
        ).items():
            exact_key_to_id.setdefault(key, node_id)
        if previous_module is not None:
            for meta in previous_metadata_map.values():
                content_key = build_exact_node_key(
                    meta.start_line,
                    meta.start_col,
                    meta.end_line,
                    meta.end_col,
                    meta.type,
                )
                exact_key_to_content.setdefault(
                    content_key,
                    normalized_source_span(
                        previous_module, meta.start_line, meta.end_line
                    ),
                )
    class_stack: List[str] = []
    func_stack: List[str] = []
    node_to_uuid: Dict[int, str] = {}

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        if max_depth is not None and depth > max_depth:
            return

        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            if depth > 0:
                for child_index, child in enumerate(node.children):
                    visit(child, depth + 1, path_indices + (child_index,))
                return

        pos = positions.get(node)
        if pos is None and isinstance(node, cst.Decorator):
            pos = positions.get(node.decorator)
        if pos is None:
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            return

        parent = parents.get(node)

        node_id: Optional[str] = None
        marker_path = build_marker_path(path_indices)
        exact_key = build_exact_node_key(
            start_line,
            start_col,
            end_line,
            end_col,
            node_type,
        )
        if persisted_node_ids and marker_path in persisted_node_ids:
            node_id = persisted_node_ids[marker_path]
        elif exact_key in exact_key_to_id:
            candidate_id = exact_key_to_id.pop(exact_key)
            prior_content = exact_key_to_content.pop(exact_key, None)
            if prior_content is None:
                # No previous_module supplied for content verification (legacy
                # callers): keep the pre-existing position-only behavior.
                node_id = candidate_id
            else:
                current_content = normalized_source_span(
                    tree.module, start_line, end_line
                )
                if current_content == prior_content:
                    node_id = candidate_id
                # else: a different statement/node now occupies this exact
                # coordinate span (line shift after a structural edit) -- do
                # not let it inherit candidate_id; mint a fresh identity below.
        elif (
            pinned_node_id
            and previous_metadata_map
            and pinned_node_id in previous_metadata_map
        ):
            pin_meta = previous_metadata_map[pinned_node_id]
            if (
                node_type == pin_meta.type
                and start_line == pin_meta.start_line
                and start_col == pin_meta.start_col
            ):
                node_id = pinned_node_id
        if node_id is None:
            node_id = _deterministic_fresh_node_id(
                tree.file_path,
                node_type,
                start_line,
                start_col,
                end_line,
                end_col,
                normalized_source_span(tree.module, start_line, end_line),
                marker_path,
            )
        node_to_uuid[id(node)] = node_id

        tree.node_map[node_id] = node
        parent_id = node_to_uuid.get(id(parent)) if parent else None
        tree.parent_map[node_id] = parent_id

        name = get_node_name(node)
        qualname = get_node_qualname(node, class_stack, func_stack)
        kind = get_node_kind(node, class_stack)
        prev_meta = (
            previous_metadata_map.get(node_id) if previous_metadata_map else None
        )
        if prev_meta is not None and (
            prev_meta.name != name or prev_meta.type != node_type
        ):
            prev_meta = None
        carried_stable_id = _get_stable_id_from_node(node)
        if node_type in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            stable_id = (
                carried_stable_id
                or (
                    obj_to_stable.get(("qualname", qualname))
                    if obj_to_stable and qualname
                    else None
                )
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        else:
            stmt_sk = None
            if obj_to_stable and node_type in _STATEMENT_STABLE_TYPES:
                norm = normalized_source_span(tree.module, start_line, end_line)
                if norm:
                    stmt_sk = build_statement_stable_key(node_type, qualname, norm)
            stable_id = (
                carried_stable_id
                or (obj_to_stable.get(stmt_sk) if stmt_sk else None)
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        if isinstance(node, cst.Decorator):
            parent_cst = parents.get(node)
            if isinstance(parent_cst, (cst.FunctionDef, cst.ClassDef)):
                dec_index = next(
                    (i for i, d in enumerate(parent_cst.decorators) if d is node),
                    0,
                )
                parent_qual = get_node_qualname(parent_cst, class_stack, func_stack)
                if not prev_meta or not prev_meta.stable_id:
                    stable_id = decorator_stable_id(parent_qual, dec_index)

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        children_ids = (
            [node_to_uuid[id(c)] for c in node.children if id(c) in node_to_uuid]
            if include_children
            else []
        )

        metadata = TreeNodeMetadata(
            node_id=node_id,
            stable_id=stable_id,
            type=node_type,
            kind=kind,
            name=name,
            qualname=qualname,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            children_count=len(children_ids),
            children_ids=children_ids,
            parent_id=parent_id,
        )
        tree.metadata_map[node_id] = metadata
        if depth == 0:
            tree.root_node_id = node_id

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0, (0,))
