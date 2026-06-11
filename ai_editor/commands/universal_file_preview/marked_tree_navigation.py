"""
PreviewNavigation adapter for universal_file_preview (G-004 {f001}, {f002}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_editor.tree.contracts import NodeId
from ai_editor.tree.preview_navigation import (
    PreviewNavigation,
    PreviewNavigationError,
    PreviewTextMode,
    _build_indexes,
    _iter_all_nodes,
    apply_line_id_prefixes,
    compute_line_span,
    compute_max_short_id_in_tree,
)
from ai_editor.tree.preview_selector import (
    DEFAULT_FULL_TEXT_MAX_LINES,
    PreviewSelector,
    PreviewSelectorConfig,
    PreviewSelectorError,
    format_key_from_extension,
)

from .base_handler import FileHandler
from .budget import PreviewBudget
from .errors import (
    INPUT_ERROR_INVALID_SELECTOR_FORM,
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from .handlers.jsonl_handler import JsonLinesFileHandler
from .marked_tree_loader import (
    _read_source_text,
    make_preview_tree_loader,
    parse_focus_short_id,
    resolve_format_handler,
)
from .models import Block, NavigationResult, Node, NodeKind
from .node_ref_params import normalize_optional_node_ref
from .invalid_preview import invalid_source_node

from .tree_temp_preview_focus import looks_like_sidecar_stable_id

_PYTHON_EXTENSIONS = frozenset({".py", ".pyi", ".pyw"})
_SCALAR_KINDS = frozenset({"scalar", "string", "number", "boolean", "null"})


def looks_like_json_pointer_node_ref(node_ref: object) -> bool:
    """True when ``node_ref`` is RFC 6901-style (tree-temp / legacy preview)."""
    if not isinstance(node_ref, str):
        return False
    return bool(node_ref.strip().startswith("/"))


def _preview_source_is_parseable(params: dict[str, Any]) -> bool:
    """Return False when marked-tree loader would fail on broken JSON/YAML source."""
    preview_path = Path(str(params.get("file_path", "")))
    if not preview_path.is_file():
        return True
    content = _read_source_text(preview_abs_path=preview_path)
    if not content.strip():
        return True
    ext = preview_path.suffix.lower()
    if ext in _PYTHON_EXTENSIONS:
        try:
            import libcst as cst

            cst.parse_module(content)
            return True
        except Exception:
            return False
    try:
        resolve_format_handler(preview_path).parse_content(preview_path, content)
        return True
    except Exception:
        return False


def marked_tree_node_ref_is_ready(params: dict[str, Any]) -> bool:
    """Return True when ``node_ref`` is absent or resolved to integer short_id."""
    node_ref = normalize_optional_node_ref(params.get("node_ref"))
    if node_ref is None:
        return True
    return str(node_ref).strip().isdigit()


def resolve_session_pointer_node_ref(params: dict[str, Any]) -> None:
    """Map JSON Pointer ``node_ref`` to integer short_id for valid edit sessions."""
    node_ref = params.get("node_ref")
    if not looks_like_json_pointer_node_ref(node_ref):
        return
    session_id = params.get("session_id")
    if session_id is None:
        return
    from ai_editor.commands.universal_file_edit.session import get_session
    from ai_editor.core.edit_session.edit_operations_adapter import (
        resolve_node_ref_to_short_id,
    )
    from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file

    try:
        edit_sess = get_session(str(session_id))
        core = edit_sess.core
        if not core.session_tree_path.is_file():
            return
        sections = parse_tree_file(core.session_tree_path.read_text(encoding="utf-8"))
        short_id = resolve_node_ref_to_short_id(
            str(node_ref),
            sections,
            source_abs=core.source_abs,
            unmarked_source=core.session_source_path.read_text(encoding="utf-8"),
            handler_id=edit_sess.handler_id,
        )
        params["node_ref"] = str(short_id)
    except Exception:
        return


def should_use_marked_tree_navigation(
    handler: FileHandler,
    params: dict[str, Any],
) -> bool:
    """Return True when PreviewNavigation + TreeLifecycle should handle the request."""
    file_path = Path(str(params.get("file_path", "")))
    ext = file_path.suffix.lower()
    if ext in _PYTHON_EXTENSIONS:
        if not params.get("project_root") or not params.get("rel_file_path"):
            return False
        try:
            resolve_format_handler(file_path)
        except Exception:
            return False
        return True

    if isinstance(handler, JsonLinesFileHandler):
        return False
    if params.get("tree_temp_roots") is not None:
        return False
    node_ref = params.get("node_ref")
    if looks_like_sidecar_stable_id(node_ref if isinstance(node_ref, str) else None):
        return False
    if looks_like_json_pointer_node_ref(node_ref) and params.get("session_id") is None:
        return False
    if not _preview_source_is_parseable(params):
        return False
    if isinstance(params.get("selector"), list) and params["selector"]:
        first = params["selector"][0]
        if isinstance(first, str):
            return False
    if not params.get("project_root") or not params.get("rel_file_path"):
        return False
    try:
        resolve_format_handler(file_path)
    except Exception:
        return False
    return True


def _kind_to_node_kind(kind: str) -> NodeKind:
    normalized = (kind or "").lower()
    if normalized in _SCALAR_KINDS:
        return NodeKind.SCALAR
    if normalized in ("object", "mapping"):
        return NodeKind.MAPPING
    if normalized == "array":
        return NodeKind.SEQUENCE
    if normalized == "sequence":
        return NodeKind.SEQUENCE
    if normalized == "lines":
        return NodeKind.LINES
    return NodeKind.TREE_NODE


def _scalar_display_value(node: Any) -> str | None:
    """Extract a legacy-style ``attributes.value`` string for scalar focus nodes."""
    kind = str(getattr(node, "kind", "") or "")
    if kind not in _SCALAR_KINDS:
        return None
    raw_content = getattr(node, "content", None)
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        text = raw_content.strip()
        if text.endswith("..."):
            text = text[:-3].strip()
        return text
    if parsed is None:
        return "null"
    if isinstance(parsed, bool):
        return "true" if parsed else "false"
    if isinstance(parsed, str):
        return parsed
    return str(parsed)


def _tree_node_to_preview_node(node: Any) -> Node:
    attrs = dict(getattr(node, "attributes", None) or {})
    kind = str(getattr(node, "kind", "") or "")
    short_id = int(getattr(node, "short_id"))
    name = attrs.get("name")
    if name is not None and not isinstance(name, str):
        name = str(name)
    scalar_value = _scalar_display_value(node)
    if scalar_value is not None and "value" not in attrs:
        attrs["value"] = scalar_value
    return Node(
        node_kind=_kind_to_node_kind(kind),
        node_ref=str(short_id),
        type_label=kind,
        name=name if isinstance(name, str) else None,
        attributes=attrs,
    )


def _preview_block_record_to_block(record: Any) -> Block:
    sid = int(record.short_id)
    kind = str(record.type_label or "")
    summary: dict[str, Any] = {
        "type": kind,
        "short_id": sid,
        "attribute_summary": record.attribute_summary,
        "render_mode": record.render_mode.value,
        "line_span": record.line_span,
    }
    return Block(
        node_kind=_kind_to_node_kind(kind),
        node_ref=str(sid),
        summary=summary,
        text=record.text_excerpt or None,
    )


def _document_level_blocks(tree: Any) -> list[Any]:
    """Top-level nodes for root_view when the marked tree has no single container root."""
    nodes = list(_iter_all_nodes(tree))
    return sorted(
        [n for n in nodes if getattr(n, "parent_short_id", None) is None],
        key=lambda n: int(getattr(n, "short_id", 0)),
    )


def _document_line_to_short_id(tree: Any) -> dict[int, NodeId]:
    mapping: dict[int, NodeId] = {}
    for node in _iter_all_nodes(tree):
        attrs = getattr(node, "attributes", None) or {}
        start = attrs.get("start_line")
        end = attrs.get("end_line")
        sid = getattr(node, "short_id", None)
        if (
            not isinstance(sid, int)
            or not isinstance(start, int)
            or not isinstance(end, int)
        ):
            continue
        if start < 1 or end < start:
            continue
        node_id = NodeId(sid)
        for line_no in range(start, end + 1):
            mapping[line_no] = node_id
    return mapping


def _root_view_block_set(
    tree: Any,
    navigation: PreviewNavigation,
    focus_short_id: NodeId,
) -> list[Any]:
    """Blocks for omitted node_ref.

    Single-container trees (JSON/YAML object root): children of that root.
    Multi-root trees (Python module statements): all top-level document nodes.
    """
    doc_blocks = _document_level_blocks(tree)
    if len(doc_blocks) > 1:
        return doc_blocks
    try:
        children = navigation._enumerate_children(tree, focus_short_id)
    except PreviewNavigationError:
        children = []
    if children:
        return children
    return doc_blocks


def _enrich_focus_for_root_view(
    focus_node: Node,
    *,
    tree: Any,
    source_text: str,
    format_key: str,
    budget: PreviewBudget,
    config: PreviewSelectorConfig,
    preview_abs_path: Path,
    max_short_id: int,
) -> None:
    """Populate ``focus.text`` / ``attributes.full_text`` for root_view."""
    attrs = dict(focus_node.attributes or {})
    threshold = config.full_text_max_lines.get(format_key, DEFAULT_FULL_TEXT_MAX_LINES)
    if threshold <= 0 or not source_text.strip():
        return
    if compute_line_span(source_text) >= threshold:
        return
    line_map = _document_line_to_short_id(tree)
    annotated = apply_line_id_prefixes(
        source_text,
        line_map,
        mode=PreviewTextMode.ANNOTATED,
        max_short_id=max_short_id,
    )
    attrs["text"] = annotated
    attrs["full_text"] = True
    focus_node.attributes = attrs


def navigate_marked_tree(
    params: dict[str, Any],
    budget: PreviewBudget,
) -> NavigationResult | PreviewError:
    """Run PreviewNavigation with TreeLifecycle-backed tree_loader."""
    project_root = Path(str(params["project_root"]))
    rel_file_path = str(params["rel_file_path"])
    preview_abs_path = Path(str(params["file_path"]))
    session_id = params.get("session_id")
    if session_id is not None:
        session_id = str(session_id)

    loader = make_preview_tree_loader(
        project_root=project_root,
        rel_file_path=rel_file_path,
        preview_abs_path=preview_abs_path,
        bound_session_id=session_id,
    )
    try:
        tree = loader(preview_abs_path, session_id)
    except Exception as exc:
        invalid = invalid_source_node(str(preview_abs_path), exc)
        return NavigationResult(
            focus_node=invalid,
            total_blocks=0,
            selected_blocks=[],
            tree_id=None,
            short_id_refs=True,
        )
    root_view = normalize_optional_node_ref(params.get("node_ref")) is None
    try:
        focus_short_id = parse_focus_short_id(params.get("node_ref"), tree.nodes)
    except ValueError as exc:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            str(exc),
            details={"node_ref": params.get("node_ref")},
        )

    raw_selector = params.get("selector")
    if raw_selector is None:
        selector: str | list[int] | None = f"0:{budget.preview_lines}"
    else:
        selector = raw_selector

    format_key = format_key_from_extension(preview_abs_path.suffix)
    config = PreviewSelectorConfig(
        full_text_max_lines={format_key: budget.full_text_max_lines},
    )
    navigation = PreviewNavigation(tree_loader=loader)
    max_short_id = compute_max_short_id_in_tree(tree)
    source_text = _read_source_text(preview_abs_path=preview_abs_path)

    try:
        if root_view:
            block_set = _root_view_block_set(tree, navigation, focus_short_id)
            parsed = PreviewSelector.parse(selector)
            selected = parsed.apply(block_set)
            selected_blocks = [
                _preview_block_record_to_block(
                    navigation._render_block(
                        block,
                        format_key=format_key,
                        config=config,
                        text_mode=PreviewTextMode.ANNOTATED,
                        source_path=preview_abs_path,
                        max_short_id=max_short_id,
                    )
                )
                for block in selected
            ]
            total_blocks = len(block_set)
        else:
            result = navigation.navigate(
                source_path=preview_abs_path,
                focus_short_id=focus_short_id,
                selector=selector,
                session_id=session_id,
                config=config,
                text_mode=PreviewTextMode.ANNOTATED,
            )
            selected_blocks = [_preview_block_record_to_block(b) for b in result.blocks]
            total_blocks = len(navigation._enumerate_children(tree, focus_short_id))
    except PreviewNavigationError as exc:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            str(exc),
            details={"node_ref": params.get("node_ref")},
        )
    except PreviewSelectorError as exc:
        return input_error(
            INPUT_ERROR_INVALID_SELECTOR_FORM,
            str(exc),
            details={"selector": raw_selector},
        )

    _, by_short_id, _ = _build_indexes(tree)
    focus_node_raw = by_short_id.get(focus_short_id)
    if focus_node_raw is None:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            f"unknown short_id: {focus_short_id!r}",
            details={"node_ref": params.get("node_ref")},
        )
    focus_node = _tree_node_to_preview_node(focus_node_raw)
    if root_view:
        _enrich_focus_for_root_view(
            focus_node,
            tree=tree,
            source_text=source_text,
            format_key=format_key,
            budget=budget,
            config=config,
            preview_abs_path=preview_abs_path,
            max_short_id=max_short_id,
        )
    return NavigationResult(
        focus_node=focus_node,
        total_blocks=total_blocks,
        selected_blocks=selected_blocks,
        tree_id=None,
        short_id_refs=True,
    )
