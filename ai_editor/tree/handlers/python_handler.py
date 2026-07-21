"""
Python FormatHandler — hybrid integer marker contract per {b005} (C-007).

Markers are embedded in the ``.py.tree`` TREE section only; SourceFile ``.py``
bytes on disk are never modified by this handler. ``parse_content`` uses the
``cst_tree`` builder oracle with ``persist_sidecar=False`` (no ``.cst/`` JSON
sidecar). G1-13 deferral is resolved in ``marked_tree_unification``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, TypeVar, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from ai_editor.core.cst_tree.models import (
    CSTTree,
    TreeNodeMetadata,
    TreeOperation,
    TreeOperationType,
)
from ai_editor.core.cst_tree.node_type_utils import get_node_kind
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code
from ai_editor.core.cst_tree.tree_modifier import (
    _apply_operation,
    _find_parent_for_node,
)
from ai_editor.core.cst_tree.tree_stable_data import (
    extract_stable_data,
    restore_stable_data,
)
from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.format_handler import FormatHandler, ShortIdAllocator
from ai_editor.tree.tree_node import TreeNode

_METADATA_ID_KEY = "___id___"
_META_KEY = "___meta___"
_ORIGINAL_COMMENT_META_KEY = "original_comment"
_ORIGINAL_COMMENT_WS_META_KEY = "original_comment_ws"
_TRAILING_ID_COMMENT_RE = re.compile(r"\s+# ___id___:\d+(?: ___meta___:\{[^}]*\})?\s*$")
_ID_COMMENT_VALUE_RE = re.compile(r"# ___id___:(\d+)")
_META_IN_COMMENT_RE = re.compile(r"___meta___:(\{[^}]*\})")
_ADDRESSABLE_TYPES: Set[str] = {
    "FunctionDef",
    "AsyncFunctionDef",
    "ClassDef",
    "Decorator",
    "SimpleStatementLine",
    "Expr",
    "AnnAssign",
    "Assign",
    "AugAssign",
}
_LEAF_TYPES: Set[str] = {
    "Decorator",
    "SimpleStatementLine",
    "Expr",
    "AnnAssign",
    "Assign",
    "AugAssign",
}
_VALID_POSITIONS = frozenset({"before", "after", "first_child", "last_child"})
_CSTNodeT = TypeVar("_CSTNodeT", bound=cst.CSTNode)
_DEF_CLASS_CST_TYPES: Tuple[type, ...] = (cst.FunctionDef, cst.ClassDef)
if hasattr(cst, "AsyncFunctionDef"):
    _DEF_CLASS_CST_TYPES = _DEF_CLASS_CST_TYPES + (getattr(cst, "AsyncFunctionDef"),)


class PythonEditGateError(ValueError):
    """Raised when short_id edit ops run while tree is invalid."""


def _short_id_from_comment_value(value: str) -> Optional[int]:
    match = _ID_COMMENT_VALUE_RE.search(value)
    return int(match.group(1)) if match else None


def _extra_meta_from_comment_value(value: str) -> Dict[str, Any]:
    match = _META_IN_COMMENT_RE.search(value)
    if match is None:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _format_marker_comment(
    sid: int, extra_meta: Optional[Dict[str, Any]] = None
) -> str:
    comment = f"# ___id___:{sid}"
    if extra_meta:
        comment += f" ___meta___:{json.dumps(extra_meta, sort_keys=True, separators=(',', ':'))}"
    return comment


def _extra_meta_from_cst_node(node: cst.CSTNode) -> Dict[str, Any]:
    metadata = getattr(node, "metadata", None)
    if isinstance(metadata, dict):
        stored = metadata.get(_META_KEY)
        if isinstance(stored, dict):
            return dict(stored)
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock) and body.header.comment is not None:
            return _extra_meta_from_comment_value(body.header.comment.value)
    tw = getattr(node, "trailing_whitespace", None)
    if tw is not None and tw.comment is not None:
        return _extra_meta_from_comment_value(tw.comment.value)
    return {}


def _collect_sid_extra_meta(marked_text: str) -> Dict[int, Dict[str, Any]]:
    module = cst.parse_module(marked_text)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: Dict[int, Dict[str, Any]] = {}

    class _MetaCollector(cst.CSTVisitor):
        def on_leave(self, node: cst.CSTNode) -> None:
            tname = type(node).__name__
            if tname not in _ADDRESSABLE_TYPES:
                return
            sid = _short_id_from_cst_node(node)
            if sid is None:
                return
            extra = _extra_meta_from_cst_node(node)
            if extra:
                result[sid] = extra

    module.visit(_MetaCollector())
    _ = positions
    return result


def _short_id_from_cst_node(node: cst.CSTNode) -> Optional[int]:
    metadata = getattr(node, "metadata", None)
    if isinstance(metadata, dict) and _METADATA_ID_KEY in metadata:
        return int(metadata[_METADATA_ID_KEY])
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock) and body.header.comment is not None:
            sid = _short_id_from_comment_value(body.header.comment.value)
            if sid is not None:
                return sid
    tw = getattr(node, "trailing_whitespace", None)
    if tw is not None and tw.comment is not None:
        return _short_id_from_comment_value(tw.comment.value)
    return None


class _MarkedShortIdCollector(cst.CSTVisitor):
    def __init__(self, positions: Mapping[cst.CSTNode, Any]) -> None:
        self._positions = positions
        self.entries: List[Tuple[int, int, str]] = []

    def on_leave(self, node: cst.CSTNode) -> None:
        tname = type(node).__name__
        if tname not in _ADDRESSABLE_TYPES:
            return
        sid = _short_id_from_cst_node(node)
        if sid is None:
            return
        pos = self._positions.get(node)
        if pos is not None:
            self.entries.append((sid, pos.start.line, tname))


def _extract_line_span(content: str, start_line: int, end_line: int) -> str:
    """Return 1-based inclusive line span from *content*, preserving line endings."""
    lines = content.splitlines(keepends=True)
    if not lines or start_line < 1:
        return ""
    lo = start_line - 1
    hi = min(len(lines), end_line)
    if lo >= hi:
        return ""
    return "".join(lines[lo:hi])


def _is_shebang_line(content: str, start_line: int) -> bool:
    lines = content.splitlines()
    if start_line != 1 or not lines:
        return False
    return lines[0].lstrip().startswith("#!")


def _comment_trailing(
    existing: cst.TrailingWhitespace,
    sid: int,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> cst.TrailingWhitespace:
    """Attach the ``___id___`` marker comment, preserving whitespace-before-comment.

    The marker replaces any real inline comment, stashing its text (and the exact
    whitespace run that preceded it, e.g. two spaces for PEP 8 ``  # ...``) inside
    ``extra_meta``. On every subsequent re-mark pass — after a structural mutation
    elsewhere in the tree strips the header down to bare whitespace — the stored
    whitespace is replayed instead of collapsing to a hardcoded single space, which
    previously caused flake8 E261 on untouched sibling declarations (bug ed579e33).

    Args:
        existing: Current trailing-whitespace/comment node (may already be a marker,
            already stripped to no comment, or carrying the real original comment).
        sid: Integer short_id to embed in the marker comment.
        extra_meta: Carried-forward marker metadata (``original_comment`` /
            ``original_comment_ws`` and any caller-supplied extras); merged with
            whatever this call newly captures from *existing*.

    Returns:
        A new ``TrailingWhitespace`` carrying the marker comment.
    """
    ws = existing.whitespace
    meta = dict(extra_meta or {})
    if existing.comment is not None and not _ID_COMMENT_VALUE_RE.search(
        existing.comment.value
    ):
        meta.setdefault(_ORIGINAL_COMMENT_META_KEY, existing.comment.value)
        if ws.value:
            meta.setdefault(_ORIGINAL_COMMENT_WS_META_KEY, ws.value)
    if not ws.value:
        stored_ws = meta.get(_ORIGINAL_COMMENT_WS_META_KEY)
        ws = (
            cst.SimpleWhitespace(stored_ws)
            if isinstance(stored_ws, str) and stored_ws
            else cst.SimpleWhitespace(" ")
        )
    return cst.TrailingWhitespace(
        whitespace=ws,
        comment=cst.Comment(_format_marker_comment(sid, meta or None)),
        newline=existing.newline,
    )


def _clear_id_comment_trailing(tw: cst.TrailingWhitespace) -> cst.TrailingWhitespace:
    """Remove ``___id___`` marker comment and padding space added for libcst."""
    if tw.comment is None or not _ID_COMMENT_VALUE_RE.search(tw.comment.value):
        return tw
    extra = _extra_meta_from_comment_value(tw.comment.value)
    original_comment = extra.get(_ORIGINAL_COMMENT_META_KEY)
    if isinstance(original_comment, str) and original_comment.startswith("#"):
        return tw.with_changes(comment=cst.Comment(original_comment))
    ws = tw.whitespace
    if ws.value == " ":
        ws = cst.SimpleWhitespace("")
    return tw.with_changes(comment=None, whitespace=ws)


def _try_attach_metadata(
    node: _CSTNodeT, sid: int, extra_meta: Optional[Dict[str, Any]] = None
) -> Optional[_CSTNodeT]:
    """Set ``metadata[___id___]`` when the CST node type supports metadata dicts."""
    existing = getattr(node, "metadata", None)
    merged: Dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    merged[_METADATA_ID_KEY] = sid
    if extra_meta:
        merged[_META_KEY] = dict(extra_meta)
    elif _META_KEY in merged:
        del merged[_META_KEY]
    try:
        return cast(_CSTNodeT, node.with_changes(metadata=merged))
    except TypeError:
        return None


def _attach_metadata_marker(
    node: _CSTNodeT, sid: int, extra_meta: Optional[Dict[str, Any]] = None
) -> _CSTNodeT:
    """Attach integer short_id: metadata dict first, trailing comment fallback."""
    if extra_meta is None:
        attached = _try_attach_metadata(node, sid)
        if attached is not None:
            return attached
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            header = body.header
            new_body = body.with_changes(
                header=_comment_trailing(header, sid, extra_meta)
            )
            return cast(_CSTNodeT, node.with_changes(body=new_body))
        return node
    if isinstance(node, cst.Decorator):
        tw = node.trailing_whitespace
        return cast(
            _CSTNodeT,
            node.with_changes(
                trailing_whitespace=_comment_trailing(tw, sid, extra_meta)
            ),
        )
    return node


def _attach_trailing_marker(
    node: _CSTNodeT, sid: int, extra_meta: Optional[Dict[str, Any]] = None
) -> _CSTNodeT:
    if not hasattr(node, "trailing_whitespace"):
        return node
    tw = node.trailing_whitespace
    if tw.comment is not None and extra_meta is None:
        return node
    return cast(
        _CSTNodeT,
        node.with_changes(trailing_whitespace=_comment_trailing(tw, sid, extra_meta)),
    )


def _clear_metadata_marker(node: _CSTNodeT) -> _CSTNodeT:
    metadata = getattr(node, "metadata", None)
    if isinstance(metadata, dict) and _METADATA_ID_KEY in metadata:
        cleaned = dict(metadata)
        del cleaned[_METADATA_ID_KEY]
        try:
            return cast(_CSTNodeT, node.with_changes(metadata=cleaned or None))
        except TypeError:
            pass
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            header = body.header
            if header.comment is not None and _ID_COMMENT_VALUE_RE.search(
                header.comment.value
            ):
                new_header = _clear_id_comment_trailing(header)
                new_body = body.with_changes(header=new_header)
                return cast(_CSTNodeT, node.with_changes(body=new_body))
        return node
    if isinstance(node, cst.Decorator):
        tw = node.trailing_whitespace
        if tw.comment is not None and _ID_COMMENT_VALUE_RE.search(tw.comment.value):
            return cast(
                _CSTNodeT,
                node.with_changes(trailing_whitespace=_clear_id_comment_trailing(tw)),
            )
    return node


def _clear_trailing_marker(node: _CSTNodeT) -> _CSTNodeT:
    if not hasattr(node, "trailing_whitespace"):
        return node
    tw = node.trailing_whitespace
    if tw.comment is not None and _ID_COMMENT_VALUE_RE.search(tw.comment.value):
        return cast(
            _CSTNodeT,
            node.with_changes(trailing_whitespace=_clear_id_comment_trailing(tw)),
        )
    return node


class _MarkTransformer(cst.CSTTransformer):
    def __init__(self, allocator: ShortIdAllocator) -> None:
        self._allocator = allocator

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return _attach_metadata_marker(updated_node, self._allocator.allocate())

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        return _attach_metadata_marker(updated_node, self._allocator.allocate())

    def leave_Decorator(
        self, original_node: cst.Decorator, updated_node: cst.Decorator
    ) -> cst.Decorator:
        return _attach_metadata_marker(updated_node, self._allocator.allocate())

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.SimpleStatementLine:
        return _attach_trailing_marker(updated_node, self._allocator.allocate())

    def leave_Expr(self, original_node: cst.Expr, updated_node: cst.Expr) -> cst.Expr:
        return _attach_trailing_marker(updated_node, self._allocator.allocate())

    def leave_AnnAssign(
        self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign
    ) -> cst.AnnAssign:
        return _attach_trailing_marker(updated_node, self._allocator.allocate())

    def leave_Assign(
        self, original_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.Assign:
        return _attach_trailing_marker(updated_node, self._allocator.allocate())

    def leave_AugAssign(
        self, original_node: cst.AugAssign, updated_node: cst.AugAssign
    ) -> cst.AugAssign:
        return _attach_trailing_marker(updated_node, self._allocator.allocate())


class _UnmarkTransformer(cst.CSTTransformer):
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return _clear_metadata_marker(updated_node)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        return _clear_metadata_marker(updated_node)

    def leave_Decorator(
        self, original_node: cst.Decorator, updated_node: cst.Decorator
    ) -> cst.Decorator:
        return _clear_metadata_marker(updated_node)

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.SimpleStatementLine:
        return _clear_trailing_marker(updated_node)

    def leave_Expr(self, original_node: cst.Expr, updated_node: cst.Expr) -> cst.Expr:
        return _clear_trailing_marker(updated_node)

    def leave_AnnAssign(
        self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign
    ) -> cst.AnnAssign:
        return _clear_trailing_marker(updated_node)

    def leave_Assign(
        self, original_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.Assign:
        return _clear_trailing_marker(updated_node)

    def leave_AugAssign(
        self, original_node: cst.AugAssign, updated_node: cst.AugAssign
    ) -> cst.AugAssign:
        return _clear_trailing_marker(updated_node)


def _index_short_ids(marked_text: str, tree: CSTTree) -> Dict[int, str]:
    """Map short_id -> stable_id from marked TREE text and indexed CSTTree."""
    module = cst.parse_module(marked_text)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    collector = _MarkedShortIdCollector(positions)
    module.visit(collector)
    index: Dict[int, str] = {}
    for sid, line, tname in collector.entries:
        for meta in tree.metadata_map.values():
            if meta.start_line == line and meta.type == tname and meta.stable_id:
                index[sid] = meta.stable_id
                break
    return index


def _stable_to_internal(tree: CSTTree, stable_id: str) -> str:
    meta = tree.find_by_stable_id(stable_id)
    if meta is None:
        raise ValueError(f"stable_id not found in tree: {stable_id!r}")
    if meta.type == "IndentedBlock":
        raise ValueError("IndentedBlock cannot be edit target")
    return meta.node_id


def _require_node_id(tree: CSTTree, short_id: NodeId, sid_index: Dict[int, str]) -> str:
    stable = sid_index.get(int(short_id))
    if stable is None:
        raise UnknownNodeIdError(short_id)
    return _stable_to_internal(tree, stable)


def _load_marked_tree(marked_text: str) -> Tuple[CSTTree, Dict[int, str]]:
    clean = _strip_trailing_id_comments(marked_text)
    tree = create_tree_from_code(
        "<python_tree_edit>",
        clean,
        persist_sidecar=False,
        register_in_memory=False,
    )
    return tree, _index_short_ids(marked_text, tree)


def _mutate_tree(tree: CSTTree, operation: TreeOperation) -> CSTTree:
    previous_metadata_map = dict(tree.metadata_map)
    previous_module = tree.module
    decorator_map = extract_stable_data(tree)
    pinned = (
        operation.node_id if operation.action is TreeOperationType.REPLACE else None
    )
    tree.module = _apply_operation(tree.module, tree, operation)
    return restore_stable_data(
        tree,
        decorator_map,
        previous_metadata_map=previous_metadata_map,
        previous_module=previous_module,
        pinned_node_id=pinned,
    )


def _statement_line_comment(node: cst.CSTNode) -> Optional[cst.Comment]:
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            return body.header.comment
    tw = getattr(node, "trailing_whitespace", None)
    if tw is not None:
        return tw.comment
    return None


def _with_statement_line_comment(
    node: cst.BaseStatement,
    comment: cst.Comment,
) -> cst.BaseStatement:
    if isinstance(node, _DEF_CLASS_CST_TYPES):
        body = node.body
        if isinstance(body, cst.IndentedBlock) and body.header.comment is None:
            header = body.header
            whitespace = header.whitespace
            if not whitespace.value:
                whitespace = cst.SimpleWhitespace(" ")
            return cast(
                cst.BaseStatement,
                node.with_changes(
                    body=body.with_changes(
                        header=header.with_changes(
                            whitespace=whitespace,
                            comment=comment,
                        )
                    )
                ),
            )
        return node
    tw = getattr(node, "trailing_whitespace", None)
    if tw is not None and tw.comment is None:
        whitespace = tw.whitespace
        if not whitespace.value:
            whitespace = cst.SimpleWhitespace(" ")
        return cast(
            cst.BaseStatement,
            node.with_changes(
                trailing_whitespace=tw.with_changes(
                    whitespace=whitespace,
                    comment=comment,
                )
            ),
        )
    return node


def _snapshot_declaration_trivia(tree: CSTTree) -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    for node_id, metadata in tree.metadata_map.items():
        if metadata.type not in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            continue
        node = tree.node_map.get(node_id)
        if not isinstance(node, _DEF_CLASS_CST_TYPES):
            continue
        row: Dict[str, Any] = {
            "leading_lines": tuple(getattr(node, "leading_lines", ())),
            "decorator_leading": tuple(
                tuple(getattr(decorator, "leading_lines", ()))
                for decorator in getattr(node, "decorators", ())
            ),
        }
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            row["body_header"] = body.header
            row["body_items"] = tuple(
                (
                    tuple(getattr(statement, "leading_lines", ())),
                    _statement_line_comment(statement),
                )
                for statement in body.body
            )
        snapshot[metadata.stable_id] = row
    return snapshot


def _apply_original_comment_metadata_to_snapshot(
    snapshot: Dict[str, Dict[str, Any]],
    *,
    sid_index: Dict[int, str],
    sid_extra_meta: Optional[Dict[int, Dict[str, Any]]],
) -> None:
    if not sid_extra_meta:
        return
    stable_to_sid = _stable_map_from_index(sid_index)
    for stable_id, row in snapshot.items():
        sid = stable_to_sid.get(stable_id)
        if sid is None:
            continue
        sid_meta = sid_extra_meta.get(sid, {})
        original_comment = sid_meta.get(_ORIGINAL_COMMENT_META_KEY)
        if not isinstance(original_comment, str) or not original_comment.startswith(
            "#"
        ):
            continue
        header = row.get("body_header")
        if isinstance(header, cst.TrailingWhitespace) and header.comment is None:
            whitespace = header.whitespace
            if not whitespace.value:
                stored_ws = sid_meta.get(_ORIGINAL_COMMENT_WS_META_KEY)
                whitespace = cst.SimpleWhitespace(
                    stored_ws if isinstance(stored_ws, str) and stored_ws else "  "
                )
            row["body_header"] = header.with_changes(
                whitespace=whitespace,
                comment=cst.Comment(original_comment),
            )


def _restore_declaration_trivia(
    tree: CSTTree, snapshot: Dict[str, Dict[str, Any]]
) -> None:
    targets: Dict[int, Dict[str, Any]] = {}
    for node_id, metadata in tree.metadata_map.items():
        row = snapshot.get(metadata.stable_id)
        node = tree.node_map.get(node_id)
        if row is not None and node is not None:
            targets[id(node)] = row
    if not targets:
        return

    class _TriviaRestorer(cst.CSTTransformer):
        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            row = targets.get(id(original_node))
            if row is None:
                return updated_node
            changes: Dict[str, Any] = {}
            if hasattr(updated_node, "leading_lines") and not getattr(
                updated_node, "leading_lines", ()
            ):
                changes["leading_lines"] = row["leading_lines"]
            if isinstance(updated_node, _DEF_CLASS_CST_TYPES):
                decorators = list(updated_node.decorators)
                for index, leading in enumerate(row["decorator_leading"]):
                    if index < len(decorators) and not decorators[index].leading_lines:
                        decorators[index] = decorators[index].with_changes(
                            leading_lines=leading
                        )
                if decorators != list(updated_node.decorators):
                    changes["decorators"] = decorators
                body = updated_node.body
                if isinstance(body, cst.IndentedBlock):
                    old_header = row.get("body_header")
                    if body.header.comment is None and old_header is not None:
                        body = body.with_changes(header=old_header)
                    old_items = row.get("body_items", ())
                    body_items = list(body.body)
                    for index, item in enumerate(body_items):
                        if index >= len(old_items):
                            break
                        leading, comment = old_items[index]
                        item_changes: Dict[str, Any] = {}
                        if not item.leading_lines and leading:
                            item_changes["leading_lines"] = leading
                        updated_item = (
                            item.with_changes(**item_changes) if item_changes else item
                        )
                        if (
                            comment is not None
                            and _statement_line_comment(updated_item) is None
                        ):
                            updated_item = _with_statement_line_comment(
                                updated_item,
                                comment,
                            )
                        if updated_item is not item:
                            body_items[index] = updated_item
                    if body_items != list(body.body):
                        body = body.with_changes(body=body_items)
                    if body != updated_node.body:
                        changes["body"] = body
            return updated_node.with_changes(**changes) if changes else updated_node

    tree.module = tree.module.visit(_TriviaRestorer())


def _operation_replaces_declaration(
    tree: CSTTree,
    operation: TreeOperation,
) -> bool:
    """Return whether *operation* should arm the declaration-trivia snapshot/restore.

    Historically gated to REPLACE-of-a-declaration only. Widened (bug ed579e33) to
    any structural mutation — INSERT or DELETE of an unrelated SIBLING can still
    cause libcst to rebuild neighboring FunctionDef/ClassDef node objects and drop
    their leading blank lines, decorator spacing, or header trivia, even though the
    declaration itself was never the edit target. ``_snapshot_declaration_trivia``
    already captures every declaration in the tree regardless of the operation's
    target, so the only thing this gate controls is whether the (cheap, and a
    no-op when nothing changed) snapshot/restore pair runs at all.

    Args:
        tree: In-memory CST tree the operation is about to mutate.
        operation: The structural TreeOperation about to run.

    Returns:
        True when the tree has at least one FunctionDef/AsyncFunctionDef/ClassDef
        and the operation is a structural mutation (insert/delete/replace).
    """
    if operation.action not in (
        TreeOperationType.INSERT,
        TreeOperationType.DELETE,
        TreeOperationType.REPLACE,
    ):
        return False
    return any(
        meta.type in ("FunctionDef", "AsyncFunctionDef", "ClassDef")
        for meta in tree.metadata_map.values()
    )


def _stable_map_from_index(sid_index: Dict[int, str]) -> Dict[str, int]:
    return {stable: sid for sid, stable in sid_index.items()}


def _assign_new_stable_ids(
    tree: CSTTree, stable_to_sid: Dict[str, int], next_free: int
) -> Dict[str, int]:
    updated = dict(stable_to_sid)
    allocator = ShortIdAllocator(next_free)
    for meta in tree.metadata_map.values():
        if meta.type not in _ADDRESSABLE_TYPES or not meta.stable_id:
            continue
        if meta.stable_id not in updated:
            updated[meta.stable_id] = allocator.allocate()
    return updated


def _emit_marked(
    tree: CSTTree,
    stable_to_sid: Dict[str, int],
    *,
    sid_extra_meta: Optional[Dict[int, Dict[str, Any]]] = None,
) -> str:
    module = tree.module
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    line_type_sid: Dict[Tuple[int, str], int] = {}
    for meta in tree.metadata_map.values():
        if meta.type not in _ADDRESSABLE_TYPES or not meta.stable_id:
            continue
        sid = stable_to_sid.get(meta.stable_id)
        if sid is not None:
            line_type_sid[(meta.start_line, meta.type)] = sid

    def _mark_node(original_node: _CSTNodeT, updated_node: _CSTNodeT) -> _CSTNodeT:
        tname = type(updated_node).__name__
        pos = positions.get(original_node)
        if pos is None:
            return updated_node
        sid = line_type_sid.get((pos.start.line, tname))
        if sid is None:
            return updated_node
        extra_meta = sid_extra_meta.get(sid) if sid_extra_meta else None
        if isinstance(updated_node, _DEF_CLASS_CST_TYPES):
            return _attach_metadata_marker(updated_node, sid, extra_meta)
        return _attach_trailing_marker(updated_node, sid, extra_meta)

    class _AssignMarkTransformer(cst.CSTTransformer):
        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.FunctionDef:
            return _mark_node(original_node, updated_node)

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            return _mark_node(original_node, updated_node)

        def leave_Decorator(
            self, original_node: cst.Decorator, updated_node: cst.Decorator
        ) -> cst.Decorator:
            return _mark_node(original_node, updated_node)

        def leave_SimpleStatementLine(
            self,
            original_node: cst.SimpleStatementLine,
            updated_node: cst.SimpleStatementLine,
        ) -> cst.SimpleStatementLine:
            return _mark_node(original_node, updated_node)

        def leave_Expr(
            self, original_node: cst.Expr, updated_node: cst.Expr
        ) -> cst.Expr:
            return _mark_node(original_node, updated_node)

        def leave_AnnAssign(
            self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign
        ) -> cst.AnnAssign:
            return _mark_node(original_node, updated_node)

        def leave_Assign(
            self, original_node: cst.Assign, updated_node: cst.Assign
        ) -> cst.Assign:
            return _mark_node(original_node, updated_node)

        def leave_AugAssign(
            self, original_node: cst.AugAssign, updated_node: cst.AugAssign
        ) -> cst.AugAssign:
            return _mark_node(original_node, updated_node)

    return module.visit(_AssignMarkTransformer()).code


def _check_position(position: str) -> None:
    if position not in _VALID_POSITIONS:
        raise ValueError(f"invalid position: {position!r}")


def _insert_operation(
    tree: CSTTree, anchor_id: str, position: str, new_content: str
) -> TreeOperation:
    if position in ("before", "after"):
        return TreeOperation(
            action=TreeOperationType.INSERT,
            code=new_content,
            target_node_id=anchor_id,
            position=position,
        )
    parent_id = anchor_id
    meta = tree.metadata_map.get(anchor_id)
    if meta is None or meta.type not in ("Module", "ClassDef", "FunctionDef"):
        resolved = _find_parent_for_node(tree, anchor_id)
        if not resolved:
            raise ValueError(f"cannot resolve insert parent for anchor {anchor_id!r}")
        parent_id = resolved
    cst_pos = "first" if position == "first_child" else "last"
    return TreeOperation(
        action=TreeOperationType.INSERT,
        code=new_content,
        parent_node_id=parent_id,
        position=cst_pos,
    )


def _move_operation(
    tree: CSTTree, node_id: str, anchor_id: str, position: str
) -> TreeOperation:
    if position in ("first_child", "last_child"):
        parent_id = anchor_id
        meta = tree.metadata_map.get(anchor_id)
        if meta is None or meta.type not in ("Module", "ClassDef", "FunctionDef"):
            resolved = _find_parent_for_node(tree, anchor_id)
            if not resolved:
                raise ValueError(f"cannot resolve move parent for anchor {anchor_id!r}")
            parent_id = resolved
        cst_pos = "first" if position == "first_child" else "last"
        return TreeOperation(
            action=TreeOperationType.MOVE,
            node_id=node_id,
            parent_node_id=parent_id,
            position=cst_pos,
        )
    move_parent = _find_parent_for_node(tree, anchor_id)
    if not move_parent:
        raise ValueError(f"cannot resolve move parent for anchor {anchor_id!r}")
    parent_id = move_parent
    anchor_meta = tree.metadata_map.get(anchor_id)
    if anchor_meta is None:
        raise ValueError(f"anchor node not found: {anchor_id!r}")
    parent_meta = tree.metadata_map.get(parent_id)
    if parent_meta is None:
        raise ValueError(f"parent node not found: {parent_id!r}")
    sibling_index = -1
    for idx, child_id in enumerate(parent_meta.children_ids):
        if child_id == anchor_id or tree.node_id_aliases.get(child_id) == anchor_id:
            sibling_index = idx
            break
    if sibling_index < 0:
        raise ValueError(f"anchor {anchor_id!r} is not a direct child of {parent_id!r}")
    if position == "before":
        after_index = sibling_index - 1 if sibling_index > 0 else None
        cst_pos = "first" if sibling_index == 0 else "after"
    else:
        after_index = sibling_index
        cst_pos = "after"
    return TreeOperation(
        action=TreeOperationType.MOVE,
        node_id=node_id,
        parent_node_id=parent_id,
        position=cst_pos,
        position_after_index=after_index,
    )


def _apply_and_emit(
    tree: CSTTree,
    sid_index: Dict[int, str],
    operation: TreeOperation,
    *,
    next_free: Optional[int] = None,
    sid_extra_meta: Optional[Dict[int, Dict[str, Any]]] = None,
) -> str:
    declaration_trivia = (
        _snapshot_declaration_trivia(tree)
        if _operation_replaces_declaration(tree, operation)
        else {}
    )
    if declaration_trivia:
        _apply_original_comment_metadata_to_snapshot(
            declaration_trivia,
            sid_index=sid_index,
            sid_extra_meta=sid_extra_meta,
        )
    tree = _mutate_tree(tree, operation)
    if declaration_trivia:
        _restore_declaration_trivia(tree, declaration_trivia)
    stable_to_sid = _stable_map_from_index(sid_index)
    if next_free is not None:
        stable_to_sid = _assign_new_stable_ids(tree, stable_to_sid, next_free)
    return _emit_marked(tree, stable_to_sid, sid_extra_meta=sid_extra_meta)


def _resolve_addressable_parent_short_id(
    internal_id: str,
    tree: CSTTree,
    internal_to_short: Dict[str, int],
) -> Optional[NodeId]:
    """Walk parent_map upward, skipping non-addressable ancestors (e.g. IndentedBlock)."""
    current = tree.parent_map.get(internal_id)
    while current:
        meta = tree.metadata_map.get(current)
        if (
            meta is not None
            and meta.type in _ADDRESSABLE_TYPES
            and current in internal_to_short
        ):
            return NodeId(internal_to_short[current])
        current = tree.parent_map.get(current)
    return None


def _internal_to_short_from_sid_index(
    tree: CSTTree, sid_index: Dict[int, str]
) -> Dict[str, int]:
    """Map span node_id -> marked short_id for parent resolution."""
    out: Dict[str, int] = {}
    for sid, stable_id in sid_index.items():
        out[_stable_to_internal(tree, stable_id)] = sid
    return out


def _strip_trailing_id_comments(source: str) -> str:
    lines = source.splitlines(keepends=True)
    out: List[str] = []
    for line in lines:
        body = line.rstrip("\n")
        suffix = line[len(body) :]
        body = _TRAILING_ID_COMMENT_RE.sub("", body)
        out.append(body + suffix)
    return "".join(out)


class PythonHandler(FormatHandler):
    def __init__(self, id_map: Any = None) -> None:
        super().__init__(id_map)
        self._tree_is_valid = True

    def set_tree_validity(self, is_valid: bool) -> None:
        self._tree_is_valid = is_valid

    def discover_marked_nodes(
        self,
        marked_text: str,
        unmarked_source: str,
        file_path: Path,
    ) -> list[Any]:
        """Build MAP ``DiscoveredNode`` rows from marked TREE short_ids (edit truth)."""
        from ai_editor.core.tree_lifecycle.node_id_map import (
            DiscoveredNode,
            compute_content_fingerprint,
        )

        del file_path
        tree, sid_index = _load_marked_tree(marked_text)
        discovered: list[DiscoveredNode] = []
        for sid in sorted(sid_index):
            stable_id = sid_index[sid]
            node_id = _stable_to_internal(tree, stable_id)
            meta = tree.metadata_map[node_id]
            cst_node = tree.node_map.get(node_id)
            kind = (
                get_node_kind(cst_node, [])
                if cst_node is not None
                else (meta.kind or meta.type)
            )
            content = _extract_line_span(
                unmarked_source, meta.start_line, meta.end_line
            )
            discovered.append(
                DiscoveredNode(
                    content_fingerprint=compute_content_fingerprint(content),
                    kind=kind,
                    marker_short_id=sid,
                    attributes={
                        "start_line": meta.start_line,
                        "end_line": meta.end_line,
                        "node_type": meta.type,
                        "internal_node_id": stable_id,
                    },
                )
            )
        return discovered

    def preview_nodes_from_marked(
        self,
        marked_text: str,
        unmarked_source: str,
        *,
        map_uuids: Optional[Dict[int, str]] = None,
    ) -> List[TreeNode]:
        """Build preview ``TreeNode`` list aligned with marked TREE short_ids."""
        tree, sid_index = _load_marked_tree(marked_text)
        internal_to_short = _internal_to_short_from_sid_index(tree, sid_index)
        nodes: List[TreeNode] = []
        for sid in sorted(sid_index):
            stable_id = sid_index[sid]
            node_id = _stable_to_internal(tree, stable_id)
            meta = tree.metadata_map[node_id]
            cst_node = tree.node_map.get(node_id)
            kind = (
                get_node_kind(cst_node, [])
                if cst_node is not None
                else (meta.kind or meta.type)
            )
            stable_ref = (map_uuids or {}).get(sid, stable_id)
            nodes.append(
                TreeNode(
                    short_id=NodeId(sid),
                    kind=kind,
                    content=_extract_line_span(
                        unmarked_source, meta.start_line, meta.end_line
                    ),
                    attributes={
                        "start_line": meta.start_line,
                        "end_line": meta.end_line,
                        "node_type": meta.type,
                        "internal_node_id": stable_ref,
                    },
                    parent_short_id=_resolve_addressable_parent_short_id(
                        node_id, tree, internal_to_short
                    ),
                )
            )
        return nodes

    def _enforce_short_id_edit_gate(self) -> None:
        if not self._tree_is_valid:
            raise PythonEditGateError(
                "tree is invalid (text mode); short_id edit operations forbidden "
                "until re-validation"
            )

    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        if content.strip() == "":
            return []
        tree: CSTTree = create_tree_from_code(
            str(file_path),
            content,
            persist_sidecar=False,
            register_in_memory=True,
        )
        allocator = ShortIdAllocator(1)
        internal_to_short: Dict[str, int] = {}
        nodes: List[TreeNode] = []
        eligible: List[tuple[str, TreeNodeMetadata]] = []
        for internal_id, meta in tree.metadata_map.items():
            if meta.type not in _ADDRESSABLE_TYPES:
                continue
            if _is_shebang_line(content, meta.start_line):
                continue
            eligible.append((internal_id, meta))
        eligible.sort(key=lambda item: (item[1].start_line, item[1].start_col))
        for internal_id, _meta in eligible:
            internal_to_short[internal_id] = allocator.allocate()
        for internal_id, meta in eligible:
            sid = internal_to_short[internal_id]
            cst_node = tree.node_map.get(internal_id)
            if cst_node is not None:
                kind = get_node_kind(cst_node, []) or meta.type
            else:
                kind = meta.kind or meta.type
            parent_short_id = _resolve_addressable_parent_short_id(
                internal_id, tree, internal_to_short
            )
            nodes.append(
                TreeNode(
                    short_id=NodeId(sid),
                    kind=kind,
                    content=_extract_line_span(content, meta.start_line, meta.end_line),
                    attributes={
                        "start_line": meta.start_line,
                        "end_line": meta.end_line,
                        "node_type": meta.type,
                        "internal_node_id": internal_id,
                    },
                    parent_short_id=parent_short_id,
                )
            )
        nodes.sort(key=lambda n: int(n.attributes.get("start_line", 0)))
        return nodes

    def mark(self, content: str) -> str:
        if content == "":
            return ""
        if content.strip() == "":
            return content
        module = cst.parse_module(content)
        marked = module.visit(_MarkTransformer(ShortIdAllocator(1)))
        return marked.code

    def unmark(self, marked_text: str) -> str:
        if marked_text == "":
            return ""
        if marked_text.strip() == "":
            return marked_text
        module = cst.parse_module(marked_text)
        cleaned = module.visit(_UnmarkTransformer())
        return _strip_trailing_id_comments(cleaned.code)

    def sidecar_path(self, source_abs: Path) -> Path:
        return source_abs.parent / (source_abs.name + ".tree")

    def op_insert(
        self,
        marked_text: str,
        anchor_short_id: NodeId,
        position: str,
        new_content: str,
        next_free: int,
    ) -> str:
        self._enforce_short_id_edit_gate()
        if next_free < 1:
            raise ValueError("next_free must be >= 1")
        _check_position(position)
        tree, sid_index = _load_marked_tree(marked_text)
        sid_extra_meta = _collect_sid_extra_meta(marked_text)
        anchor_id = _require_node_id(tree, anchor_short_id, sid_index)
        op = _insert_operation(tree, anchor_id, position, new_content)
        return _apply_and_emit(
            tree,
            sid_index,
            op,
            next_free=next_free,
            sid_extra_meta=sid_extra_meta,
        )

    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        tree, sid_index = _load_marked_tree(marked_text)
        # Collect original-comment/whitespace metadata BEFORE mutation and carry it
        # through _apply_and_emit, exactly like op_insert/op_replace — without this,
        # the whole-tree re-mark below re-attaches marker comments with no memory of
        # any declaration's real inline comment, so unrelated class/def headers lose
        # their trailing comment entirely on delete (bug ed579e33, repro B).
        sid_extra_meta = _collect_sid_extra_meta(marked_text)
        node_id = _require_node_id(tree, short_id, sid_index)
        stable = sid_index.get(int(short_id))
        op = TreeOperation(action=TreeOperationType.DELETE, node_id=node_id)
        if stable:
            sid_index = {k: v for k, v in sid_index.items() if v != stable}
        sid_extra_meta.pop(int(short_id), None)
        return _apply_and_emit(tree, sid_index, op, sid_extra_meta=sid_extra_meta)

    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        self._enforce_short_id_edit_gate()
        tree, sid_index = _load_marked_tree(marked_text)
        sid_extra_meta = _collect_sid_extra_meta(marked_text)
        node_id = _require_node_id(tree, short_id, sid_index)
        op = TreeOperation(
            action=TreeOperationType.REPLACE, node_id=node_id, code=new_content
        )
        return _apply_and_emit(tree, sid_index, op, sid_extra_meta=sid_extra_meta)

    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        tree, sid_index = _load_marked_tree(marked_text)
        node_id = _require_node_id(tree, short_id, sid_index)
        node = tree.node_map[node_id]
        return tree.module.code_for_node(node)

    def op_move(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
    ) -> str:
        self._enforce_short_id_edit_gate()
        next_free = self.peak_short_id_in_marked(marked_text) + 1
        return self.op_move_via_delete_insert(
            marked_text,
            short_id,
            anchor_short_id,
            position,
            next_free,
        )

    def op_edit_attributes(
        self, marked_text: str, short_id: NodeId, attributes: Dict[str, Any]
    ) -> str:
        self._enforce_short_id_edit_gate()
        tree, sid_index = _load_marked_tree(marked_text)
        _require_node_id(tree, short_id, sid_index)
        sid_extra_meta = _collect_sid_extra_meta(marked_text)
        merged = dict(sid_extra_meta.get(int(short_id), {}))
        merged.update(attributes)
        sid_extra_meta[int(short_id)] = merged
        return _emit_marked(
            tree,
            _stable_map_from_index(sid_index),
            sid_extra_meta=sid_extra_meta,
        )

    def op_edit_content(
        self, marked_text: str, short_id: NodeId, new_content: str
    ) -> str:
        self._enforce_short_id_edit_gate()
        tree, sid_index = _load_marked_tree(marked_text)
        node_id = _require_node_id(tree, short_id, sid_index)
        meta = tree.metadata_map.get(node_id)
        if meta is None or meta.type not in _LEAF_TYPES:
            raise ValueError("edit-content requires leaf block")
        op = TreeOperation(
            action=TreeOperationType.REPLACE, node_id=node_id, code=new_content
        )
        return _apply_and_emit(tree, sid_index, op)


if hasattr(cst, "AsyncFunctionDef"):
    _AsyncFunctionDefType = getattr(cst, "AsyncFunctionDef")

    def _mark_leave_async_function_def(
        self: _MarkTransformer,
        original_node: _AsyncFunctionDefType,
        updated_node: _AsyncFunctionDefType,
    ) -> _AsyncFunctionDefType:
        return _attach_metadata_marker(updated_node, self._allocator.allocate())

    def _unmark_leave_async_function_def(
        self: _UnmarkTransformer,
        original_node: _AsyncFunctionDefType,
        updated_node: _AsyncFunctionDefType,
    ) -> _AsyncFunctionDefType:
        return _clear_metadata_marker(updated_node)

    _MarkTransformer.leave_AsyncFunctionDef = _mark_leave_async_function_def  # type: ignore[attr-defined]
    _UnmarkTransformer.leave_AsyncFunctionDef = _unmark_leave_async_function_def  # type: ignore[attr-defined]
