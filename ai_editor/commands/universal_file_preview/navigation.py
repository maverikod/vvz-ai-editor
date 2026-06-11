"""
NavigationProcedure (C-006) for universal_file_preview.

Single three-phase function shared by all NodeKind values and all file
types: enumerate the focus node's block set, select a subset via
Selector (C-007), render each selected block via BlockHandler (C-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence, cast

from ai_editor.core.tree_temp.tree_node import TreeNode

from .base_handler import FileHandler
from .block_handlers import render_block
from .budget import PreviewBudget
from .errors import (
    INPUT_ERROR_CONFLICTING_PARAMETERS,
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from .handlers.json_handler import JsonFileHandler
from .handlers.yaml_handler import YamlFileHandler
from .models import Block, NavigationResult, Node, NodeKind
from .selector import apply_selector
from .session import resolve_session
from .node_ref_params import normalize_optional_node_ref
from .marked_tree_navigation import (
    marked_tree_node_ref_is_ready,
    navigate_marked_tree,
    resolve_session_pointer_node_ref,
    should_use_marked_tree_navigation,
)
from .tree_temp_preview_focus import (
    TreeTempPreviewResolveError,
    looks_like_sidecar_stable_id,
    resolve_tree_temp_preview_focus,
    tree_temp_preview_children_to_preview_nodes,
)

# Preview Navigation — tree-temp Sidecar / HRS (summary): Scalar ``node_ref`` (stable_id
# pointing at a Sidecar JSON string | number | boolean | null leaf) resolves to that leaf
# in the Sidecar-backed tree, walks up toward the forest root until the nearest ancestor
# whose discriminator is ``object`` or ``array``, and exposes that ancestor's ordered
# children as the preview block list. If no such ancestor exists, behavior matches
# omitting ``node_ref`` (root_view). Referencing ``object`` | ``array`` by stable_id
# drills straight into that node's children. An unknown Sidecar stable_id yields an input
# error—the scalar remap policy does not apply when the uuid is missing from the indexed
# tree.


def navigate(
    handler: FileHandler,
    params: dict[str, Any],
    budget: PreviewBudget,
) -> NavigationResult | PreviewError:
    """
    Execute the three-phase NavigationProcedure (C-006) for one request.

    Phase 1 — enumerate: produce the focus node's ordered block set.
    Phase 2 — select: apply Selector (C-007) to the block set.
    Phase 3 — render: invoke BlockHandler (C-008) for each selected block.

    Args:
        handler: FileHandler resolved by HandlerDispatcher for the file.
        params: Validated parameter dict containing keys:
                'file_path' (str), 'node_ref' (str|None),
                'selector' (str|list|None), 'project_id' (str),
                'tree_id' (str|None).
        budget: PreviewBudget with preview_lines and value_preview_len.

    Returns:
        NavigationResult on success, or PreviewError on failure.
    """
    marked_params = dict(params)
    resolve_session_pointer_node_ref(marked_params)
    use_marked_tree = should_use_marked_tree_navigation(handler, marked_params)
    if use_marked_tree and not marked_tree_node_ref_is_ready(marked_params):
        use_marked_tree = False
    if use_marked_tree:
        return navigate_marked_tree(marked_params, budget)

    ext = Path(str(params.get("file_path", ""))).suffix.lower()
    if ext in (".py", ".pyi", ".pyw"):
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "Python preview requires project_id (marked-tree navigation only).",
            details={"file_path": params.get("file_path")},
        )

    session_result = resolve_session(handler, params)
    if isinstance(session_result, PreviewError):
        return session_result
    session, session_origin, tree_id = session_result

    preview_budget = params.get("preview_budget") or budget
    open_result = handler.open_root(params["file_path"], session, budget=preview_budget)
    if isinstance(open_result, PreviewError):
        return open_result
    focus_node: Node = open_result
    node_ref_raw = normalize_optional_node_ref(params.get("node_ref"))
    roots_for_tree_preview = params.get("tree_temp_roots")
    uuid_sidecar = looks_like_sidecar_stable_id(node_ref_raw)
    tree_temp_sidecar_preview = (
        roots_for_tree_preview is not None
        and uuid_sidecar
        and isinstance(handler, (JsonFileHandler, YamlFileHandler))
    )
    if tree_temp_sidecar_preview:
        try:
            trimmed_ref = (
                node_ref_raw.strip()
                if isinstance(node_ref_raw, str)
                else str(node_ref_raw)
            )
            assert roots_for_tree_preview is not None
            focus_spec = resolve_tree_temp_preview_focus(
                roots=list(cast(Sequence[TreeNode], roots_for_tree_preview)),
                node_ref=trimmed_ref,
            )
        except TreeTempPreviewResolveError as exc:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                str(exc),
                details={"node_ref": node_ref_raw},
            )

        branches = tree_temp_preview_children_to_preview_nodes(
            list(focus_spec.container.children or [])
        )

        nc = focus_spec.navigation_context
        focus_attrs: dict[str, Any] = {
            "effective_mode": focus_spec.effective_mode,
            "resolved_stable_id": nc.get("resolved_stable_id"),
            "effective_focus_stable_id": nc.get("effective_focus_stable_id"),
            "depth_hint": nc.get("depth_hint"),
        }
        focus_node = Node(
            node_kind=NodeKind.TREE_NODE,
            node_ref=focus_spec.container.stable_id,
            type_label="tree_sidecar_focus",
            name=None,
            attributes=focus_attrs,
            _children=branches,
        )
    elif node_ref_raw is not None and not focus_node.is_invalid:
        resolve_result = handler.resolve_node_ref(node_ref_raw, session)
        if isinstance(resolve_result, PreviewError):
            return resolve_result
        focus_node = resolve_result
    block_set: list[Node] = focus_node.children
    total_blocks = len(block_set)

    selector_result = apply_selector(
        params.get("selector"), block_set, budget.preview_lines
    )
    if isinstance(selector_result, PreviewError):
        return selector_result
    selected_nodes = selector_result

    selected_blocks: list[Block] = []
    for node in selected_nodes:
        summary = render_block(node, budget.value_preview_len)
        raw_text = (node.attributes or {}).get("text")
        block_text = raw_text if isinstance(raw_text, str) else None
        selected_blocks.append(
            Block(
                node_kind=node.node_kind,
                node_ref=node.node_ref,
                summary=summary,
                text=block_text,
            )
        )

    return NavigationResult(
        focus_node=focus_node,
        total_blocks=total_blocks,
        selected_blocks=selected_blocks,
        tree_id=tree_id if session_origin == "command_created" else None,
    )
