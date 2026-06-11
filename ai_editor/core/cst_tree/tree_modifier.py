"""
CST tree modifier - modify tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import dataclasses


import logging
import hashlib

from typing import Dict, List, Optional, Tuple


import libcst as cst


from .models import (
    CSTTree,
    ROOT_NODE_ID_SENTINEL,
    TreeOperation,
    TreeOperationType,
)

from .node_id_markers import append_persisted_node_ids, strip_persisted_node_ids
from .node_stable_id import logical_source_from_module
from .tree_builder import _build_tree_index, get_tree

from .tree_metadata import _resolve_node_id as resolve_parent_id

from .tree_modifier_ops import (
    delete_node,
    insert_node_at_position,
    insert_node_relative,
    replace_node,
    replace_range,
)

from .tree_modifier_ops_parse import (
    FINE_GRAINED_REPLACE_NODE_TYPES,
    class_body_indent_prefix,
    class_or_function_snippet_needs_full_replace,
    def_snippet_container_kind,
    insert_target_container_kind,
    join_code_lines,
    parse_code_snippet_for_move,
)

from .tree_modifier_validate import _validate_operation

try:
    from ai_editor.core.mutable_cst import (
        apply_operations,
        build_from_libcst,
        serialize_to_source,
    )
except ImportError:
    build_from_libcst = None  # type: ignore[assignment]
    serialize_to_source = None  # type: ignore[assignment]
    apply_operations = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def _apply_libcst_codegen_compat() -> None:
    """
    Work around libcst codegen passing default_semicolon to nodes that do not accept it.

    In libcst 1.8.x the codegen caller may pass default_semicolon= to _codegen_impl(),
    but SimpleStatementLine._codegen_impl(self, state) does not accept it, causing
    TypeError. We wrap _codegen_impl to accept **kwargs and ignore them.
    """
    orig = cst.SimpleStatementLine._codegen_impl

    def _codegen_impl_compat(
        self: cst.SimpleStatementLine,
        state: object,
        **kwargs: object,
    ) -> None:
        orig(self, state)  # type: ignore[arg-type]

    cst.SimpleStatementLine._codegen_impl = _codegen_impl_compat  # type: ignore[method-assign]


_apply_libcst_codegen_compat()


def _use_mutable_batch_path(operations: List[TreeOperation], tree: CSTTree) -> bool:
    return False  # disabled: mutable_cst path breaks stable_id preservation
    """Use mutable CST batch path only for a single lone DELETE.

    Any other combination (multiple ops, replace+delete, insert+delete) uses
    the LibCST sequential path which produces correct class-body serialization.

    Batches that include REPLACE or DELETE targeting fine-grained node types
    (Param, Name) also use the sequential path.
    """
    if (
        build_from_libcst is None
        or serialize_to_source is None
        or apply_operations is None
    ):
        return False
    has_delete = any(op.action == TreeOperationType.DELETE for op in operations)
    has_range_or_move = any(
        op.action in (TreeOperationType.REPLACE_RANGE, TreeOperationType.MOVE)
        for op in operations
    )
    if has_range_or_move:
        return False
    for op in operations:
        if op.action not in (TreeOperationType.REPLACE, TreeOperationType.DELETE):
            continue
        nid = op.node_id
        if not nid:
            continue
        meta = tree.metadata_map.get(nid)
        if meta is None:
            continue
        node_obj = tree.node_map.get(nid)
        if node_obj is not None and isinstance(node_obj, cst.BaseExpression):
            return False
        node_type = getattr(meta, "type", "")
        if node_type and node_type in FINE_GRAINED_REPLACE_NODE_TYPES:
            return False
    # Lone single DELETE: safe for mutable path (established by BUG-002 fix).
    if has_delete and len(operations) == 1:
        return True
    # Everything else (multi-op, mixed types) → LibCST sequential path.
    return False


def _resolve_stable_node_id(tree: CSTTree, ref: str) -> str:
    """Map preview ``node_ref`` / stable_id to the current span ``node_id``."""
    if not ref or ref == ROOT_NODE_ID_SENTINEL or ":" in ref:
        return ref
    meta = tree.find_by_stable_id(ref)
    if meta is not None:
        return meta.node_id
    if ref in tree.node_map:
        return ref
    return ref


def _resolve_operation_node_ids(tree: CSTTree, op: TreeOperation) -> TreeOperation:
    """Resolve stable_id references on an operation to current span node_ids."""
    updates: Dict[str, str] = {}
    for field in (
        "node_id",
        "parent_node_id",
        "target_node_id",
        "start_node_id",
        "end_node_id",
    ):
        raw = getattr(op, field, None)
        if isinstance(raw, str) and raw:
            updates[field] = _resolve_stable_node_id(tree, raw)
    if updates:
        return dataclasses.replace(op, **updates)
    return op


def _apply_single_op(tree: CSTTree, op: TreeOperation) -> CSTTree:
    """Apply a single validated operation to a tree with full cycle."""
    from .tree_stable_data import extract_stable_data, restore_stable_data

    previous_metadata_map = dict(tree.metadata_map)
    previous_module = tree.module
    decorator_map = extract_stable_data(tree)
    pinned_node_id = op.node_id if op.action == TreeOperationType.REPLACE else None
    modified_module = _apply_operation(tree.module, tree, op)
    tree.module = modified_module
    tree = restore_stable_data(
        tree,
        decorator_map,
        previous_metadata_map=previous_metadata_map,
        previous_module=previous_module,
        pinned_node_id=pinned_node_id,
    )
    from .tree_sidecar import persist_tree_sidecar_after_edit

    persist_tree_sidecar_after_edit(tree)
    return tree


def modify_tree(tree_id: str, operations: List[TreeOperation]) -> CSTTree:
    """
    Modify tree with atomic operations.

    All operations are validated before being applied.
    If any operation fails, all changes are rolled back.

    Persisted ``stable_id`` / sidecar on disk are updated when the session is
    saved to the ``.py`` file (``cst_save_tree`` / ``save_tree_to_file``), not
    from this function alone: the on-disk checksum used by :func:`get_tree`
    still reflects the last loaded file until save refreshes it.

    Args:
        tree_id: Tree ID
        operations: List of operations to apply

    Returns:
        Modified CSTTree

    Raises:
        ValueError: If any operation is invalid
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    sorted_ops = _sort_operations_for_batch(operations, tree)
    use_mutable_batch = _use_mutable_batch_path(operations, tree)

    try:
        if use_mutable_batch:
            mutable_tree = build_from_libcst(
                tree.module, tree.metadata_map, tree.node_map
            )
            apply_operations(mutable_tree, sorted_ops, tree.metadata_map)
            source = serialize_to_source(mutable_tree)
            logical_source, persisted_node_ids = strip_persisted_node_ids(source)
            new_module = cst.parse_module(logical_source)
            _validate_module(new_module)
            tree.module = new_module
            tree.node_map.clear()
            tree.metadata_map.clear()
            tree.parent_map.clear()
            tree.node_id_aliases.clear()
            _build_tree_index(
                tree,
                node_types=None,
                max_depth=None,
                include_children=True,
                persisted_node_ids=persisted_node_ids,
            )
            tree.module_source_sha256_hex = hashlib.sha256(
                logical_source_from_module(tree.module).encode("utf-8")
            ).hexdigest()
            return tree

        modified_module = tree.module
        for op in sorted_ops:
            op = _resolve_operation_node_ids(tree, op)
            _validate_operation(tree, op)
            tree = _apply_single_op(tree, op)

        modified_module = tree.module
        _validate_module(modified_module)
        tree.module_source_sha256_hex = hashlib.sha256(
            logical_source_from_module(tree.module).encode("utf-8")
        ).hexdigest()
        return tree

    except Exception as e:
        logger.error(f"Error applying operations to tree {tree_id}: {e}")
        raise


def _sort_operations_for_batch(
    operations: List[TreeOperation], tree: CSTTree
) -> List[TreeOperation]:
    """
    Sort operations so DELETE and REPLACE run bottom-to-top (by position).
    INSERT ops run bottom-to-top by parent position.
    This prevents position shift from invalidating node references in batch.
    """
    deletes: List[Tuple[int, int, TreeOperation]] = []
    replaces: List[Tuple[int, int, TreeOperation]] = []
    inserts: List[Tuple[int, int, TreeOperation]] = []
    others: List[TreeOperation] = []
    for op in operations:
        if op.action == TreeOperationType.DELETE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            deletes.append((-line, -col, op))  # negate for descending
        elif op.action == TreeOperationType.REPLACE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            replaces.append((-line, -col, op))  # bottom-to-top
        elif op.action == TreeOperationType.INSERT and op.parent_node_id:
            meta = tree.metadata_map.get(op.parent_node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            inserts.append((-line, -col, op))  # bottom-to-top
        else:
            others.append(op)
    deletes.sort(key=lambda x: (x[0], x[1]))
    replaces.sort(key=lambda x: (x[0], x[1]))
    inserts.sort(key=lambda x: (x[0], x[1]))
    return (
        [op for (_, _, op) in deletes]
        + [op for (_, _, op) in replaces]
        + [op for (_, _, op) in inserts]
        + others
    )


def _find_parent_for_node(tree: CSTTree, node_id: str) -> Optional[str]:
    """
    Find the nearest ancestor node_id that has an insertable statement body.

    Resolves stale UUIDs via tree.node_id_aliases before lookup.
    Walks up the parent_id chain until it finds a node whose type is one of:
    Module, ClassDef, FunctionDef — i.e. a node that can serve as parent_node_id
    for insert_node_relative / insert_node_at_position (same types as preview).

    This means callers can pass any node_id (e.g. Import inside
    SimpleStatementLine, Name inside FunctionDef) and always get back a
    valid insertable container — no manual level-picking required.

    Args:
        tree: CSTTree
        node_id: Node ID to find insertable parent for

    Returns:
        Parent node_id of nearest insertable container, or None if not found
    """
    # Statement-body container types — valid parent_node_id values (not IndentedBlock)
    INSERTABLE_TYPES = {"Module", "ClassDef", "FunctionDef"}

    # Resolve alias: after insert the target node may have a new UUID
    resolved = tree.node_id_aliases.get(node_id, node_id)
    metadata = tree.metadata_map.get(resolved)
    if metadata is None and resolved != node_id:
        metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    # Walk up parent_id chain until we reach an insertable container
    current_id = metadata.parent_id
    while current_id is not None:
        current_meta = tree.metadata_map.get(current_id)
        if current_meta is None:
            break
        if current_meta.type in INSERTABLE_TYPES:
            return current_id
        current_id = current_meta.parent_id

    return None


def _replace_node_header(
    module: cst.Module,
    tree: CSTTree,
    node_id: str,
    code: str,
) -> cst.Module:
    """Replace only the header of a ClassDef or FunctionDef, preserving the body.

    Parses ``code`` as a class/function stub (with ``pass`` body if needed),
    extracts the new name, bases (for class) or params/returns (for function),
    and patches the existing LibCST node in-place, keeping its original body.

    Args:
        module: Current LibCST module.
        tree: CSTTree containing node metadata and node_map.
        node_id: ID of the ClassDef or FunctionDef node to patch.
        code: New header code, e.g. ``'class Foo(Base):'`` or
              ``'def bar(self, x: int) -> str:'``.

    Returns:
        Updated module with only the header replaced.
    """
    # Resolve node
    resolved_id = tree.node_id_aliases.get(node_id, node_id)
    old_node = tree.node_map.get(resolved_id) or tree.node_map.get(node_id)
    if old_node is None:
        raise ValueError(f"Node not found for header-replace: {node_id}")

    # Parse the new header — append a pass body so libcst accepts it
    stub = code.rstrip()
    if not stub.endswith(":"):
        stub = stub + ":"
    stub_src = stub + "\n    pass\n"
    try:
        parsed = cst.parse_module(stub_src)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Invalid header code: {exc}") from exc

    new_node_raw = parsed.body[0]

    if isinstance(old_node, cst.ClassDef) and isinstance(new_node_raw, cst.ClassDef):
        decorators = (
            old_node.decorators if old_node.decorators else new_node_raw.decorators
        )
        patched = old_node.with_changes(
            name=new_node_raw.name,
            bases=new_node_raw.bases,
            keywords=new_node_raw.keywords,
            decorators=decorators,
        )
    elif isinstance(old_node, cst.FunctionDef) and isinstance(
        new_node_raw, cst.FunctionDef
    ):
        decorators = (
            old_node.decorators if old_node.decorators else new_node_raw.decorators
        )
        patched = old_node.with_changes(
            name=new_node_raw.name,
            params=new_node_raw.params,
            returns=new_node_raw.returns,
            decorators=decorators,
        )
    else:
        # Type mismatch or unsupported node — fall back to full replace
        logger.warning(
            "_replace_node_header: node %s type mismatch (old=%s, new=%s), falling back to full replace",
            node_id,
            type(old_node).__name__,
            type(new_node_raw).__name__,
        )
        return replace_node(module, tree, node_id, code)

    # Swap the node in place using a CSTTransformer
    class _HeaderPatcher(cst.CSTTransformer):
        def __init__(self, target: cst.CSTNode, replacement: cst.CSTNode) -> None:
            self._target = target
            self._replacement = replacement
            self._replaced = False

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self._target and not self._replaced:
                self._replaced = True
                return self._replacement
            return updated_node

    patcher = _HeaderPatcher(old_node, patched)
    new_module = module.visit(patcher)
    if not patcher._replaced:
        raise ValueError(
            f"Node {node_id} (type={type(old_node).__name__}) was not patched in module. "
            "Hint: node may be stale — reload tree via cst_load_file."
        )
    # Update node_map so subsequent operations see the new node
    tree.node_map[resolved_id] = patched
    return new_module


def _apply_operation(
    module: cst.Module, tree: CSTTree, operation: TreeOperation
) -> cst.Module:
    """Apply a single operation to module."""
    if operation.action == TreeOperationType.DELETE:
        return delete_node(module, tree, operation.node_id)
    elif operation.action == TreeOperationType.REPLACE:
        code = operation.code
        if operation.code_lines:
            code = join_code_lines(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for replace operation")
        if not operation.replace_all_child_nodes:
            _nid = tree.node_id_aliases.get(operation.node_id, operation.node_id)
            _meta = tree.metadata_map.get(_nid) or tree.metadata_map.get(
                operation.node_id
            )
            if (
                _meta
                and _meta.type in ("ClassDef", "FunctionDef")
                and not class_or_function_snippet_needs_full_replace(code)
            ):
                return _replace_node_header(module, tree, operation.node_id, code)
        return replace_node(module, tree, operation.node_id, code)
    elif operation.action == TreeOperationType.REPLACE_RANGE:
        code = operation.code
        if operation.code_lines:
            code = join_code_lines(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for replace_range operation")
        if not operation.start_node_id or not operation.end_node_id:
            raise ValueError(
                "start_node_id and end_node_id required for replace_range operation"
            )
        return replace_range(
            module, tree, operation.start_node_id, operation.end_node_id, code
        )
    elif operation.action == TreeOperationType.INSERT:
        # If target_node_id is provided, find parent automatically and insert relative to target
        code = operation.code
        if operation.code_lines:
            code = join_code_lines(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for insert operation")
        if operation.target_node_id:
            parent_id = _find_parent_for_node(tree, operation.target_node_id)
            if not parent_id:
                raise ValueError(
                    f"Cannot find parent for target node: {operation.target_node_id}"
                )
            position = operation.position or "after"
            return insert_node_relative(
                module,
                tree,
                operation.target_node_id,
                parent_id,
                code,
                position,
            )
        else:
            # Use parent_node_id (with optional first/last/after N)
            if not operation.parent_node_id:
                raise ValueError(
                    "parent_node_id or target_node_id required for insert operation"
                )
            position = (operation.position or "end").strip().lower()
            parent_id_raw = operation.parent_node_id or ROOT_NODE_ID_SENTINEL
            resolved_parent = resolve_parent_id(tree, parent_id_raw)
            if not resolved_parent:
                raise ValueError(
                    f"Parent node not found: {parent_id_raw}. "
                    "Use __root__ for module-level placement."
                )
            # Map legacy "before"/"after"/"end" to first/last when no sibling index
            if operation.position_after_index is None:
                if position == "before":
                    position = "first"
                elif position in ("after", "end"):
                    position = "last"
            return insert_node_at_position(
                module,
                tree,
                resolved_parent,
                code,
                position=position,
                position_after_index=operation.position_after_index,
            )
    elif operation.action == TreeOperationType.MOVE:
        node_id = operation.node_id
        node = tree.node_map.get(node_id)
        if not node:
            raise ValueError(f"Node not found for move: {node_id}")
        source_meta = tree.metadata_map.get(node_id)
        node_type = (source_meta.type if source_meta else "") or type(node).__name__
        code = tree.module.code_for_node(node)
        parent_id_raw = (operation.parent_node_id or ROOT_NODE_ID_SENTINEL).strip()
        move_parent_id = resolve_parent_id(tree, parent_id_raw)
        if not move_parent_id:
            raise ValueError(
                f"Parent node not found for move: {parent_id_raw}. "
                "Use __root__ for module-level placement."
            )
        position = (operation.position or "last").strip().lower()
        after_index = operation.position_after_index
        target_container = insert_target_container_kind(tree, move_parent_id)
        source_container = (
            def_snippet_container_kind(tree, source_meta) if source_meta else "module"
        )
        parsed_for_insert = None
        if (
            node_type in ("FunctionDef", "ClassDef")
            or source_container != target_container
        ):
            class_indent = class_body_indent_prefix(tree, move_parent_id)
            parsed_for_insert = parse_code_snippet_for_move(
                code,
                node_type=node_type,
                target_container=target_container,
                source_container=source_container,
                class_body_indent=class_indent or "    ",
            )
        module_after_delete = delete_node(module, tree, node_id)
        return insert_node_at_position(
            module_after_delete,
            tree,
            move_parent_id,
            code,
            position=position,
            position_after_index=after_index,
            parsed_statements=parsed_for_insert,
        )
    else:
        raise ValueError(f"Unknown operation type: {operation.action}")


def _validate_module(module: cst.Module) -> None:
    """Validate module by compiling it."""
    try:
        compile(module.code, "<string>", "exec")
    except SyntaxError as e:
        raise ValueError(f"Module validation failed: {e}") from e
