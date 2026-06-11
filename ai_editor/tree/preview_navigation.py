"""
PreviewNavigation three-phase preview (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.preview_selector import (
    PreviewRenderMode,
    PreviewSelector,
    PreviewSelectorConfig,
    PreviewSelectorError,
    format_key_from_extension,
    paginate_envelope,
)

_CST_NODE_IDS_BEGIN = re.compile(r"^\s*# cst-node-ids:\s*begin\s*$", re.MULTILINE)
_CST_NODE_IDS_END = re.compile(r"^\s*# cst-node-ids:\s*end\s*$", re.MULTILINE)
_LEGACY_NODE_ID_LINE = re.compile(
    r"^\s*# @node-id:\s*[0-9a-f-]{36}\s*$", re.MULTILINE | re.IGNORECASE
)
INDENTED_BLOCK_KIND = "IndentedBlock"

_SCALAR_KINDS = frozenset(
    {"scalar", "string", "number", "boolean", "null", "integer", "float"}
)
_CONTAINER_KINDS = frozenset({"object", "array", "mapping"})


def compute_max_short_id_in_tree(tree: Any) -> int:
    """Return max short_id int in tree (minimum 1)."""
    max_sid = 1
    for node in _iter_all_nodes(tree):
        sid = getattr(node, "short_id", None)
        if isinstance(sid, int) and sid >= 1:
            max_sid = max(max_sid, sid)
    return max_sid


def compute_line_prefix_width(max_short_id: int) -> int:
    """Return len(f"[{max_short_id}] ") — dynamic digit width ({i007})."""
    if max_short_id < 1:
        raise ValueError("max_short_id must be >= 1")
    return len(f"[{max_short_id}] ")


def strip_legacy_python_identity_comments(source: str) -> str:
    """Remove legacy `# @node-id:` and `# cst-node-ids:` blocks ({i008})."""
    lines = source.splitlines(keepends=True)
    out: List[str] = []
    in_cst_block = False
    for line in lines:
        stripped = line.rstrip("\n\r")
        if _CST_NODE_IDS_BEGIN.match(stripped):
            in_cst_block = True
            continue
        if in_cst_block:
            if _CST_NODE_IDS_END.match(stripped):
                in_cst_block = False
            continue
        if _LEGACY_NODE_ID_LINE.match(stripped):
            continue
        out.append(line)
    return "".join(out)


def normalize_json_for_line_count(raw: str) -> str:
    """Pretty-print JSON before line counting ({i005})."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return json.dumps(obj, indent=2, ensure_ascii=False)


def compute_line_span(source: str) -> int:
    """Return line count for source text."""
    if not source:
        return 0
    return len(source.splitlines())


def apply_line_id_prefixes(
    source: str,
    line_to_short_id: Mapping[int, NodeId],
    *,
    mode: PreviewTextMode,
    max_short_id: int,
) -> str:
    """Prefix physical lines with `[short_id] ` or blank padding ({i007})."""
    if mode == PreviewTextMode.STRUCTURAL:
        return source
    prefix_width = compute_line_prefix_width(max_short_id)
    had_trailing_newline = source.endswith("\n")
    lines = source.splitlines(keepends=False)
    out_lines: List[str] = []
    for idx, line in enumerate(lines, start=1):
        sid = line_to_short_id.get(idx)
        if sid is not None:
            out_lines.append(f"[{sid}] {line}")
        else:
            out_lines.append((" " * prefix_width) + line)
    result = "\n".join(out_lines)
    if had_trailing_newline and (out_lines or source == "\n"):
        result += "\n"
    return result


class PreviewNavigationError(ValueError):
    """Unrecognised focus short_id."""


class PreviewTextMode(str, Enum):
    ANNOTATED = "annotated"
    FULL_TEXT = "full_text"
    STRUCTURAL = "structural"


@dataclass
class PreviewBlockRecord:
    short_id: NodeId
    type_label: str
    attribute_summary: str
    text_excerpt: str
    render_mode: PreviewRenderMode
    line_span: int


@dataclass
class PreviewNavigationResult:
    focus_short_id: NodeId
    blocks: List[PreviewBlockRecord]
    serialized_envelope: str


class PreviewNavigation:
    """Three-phase preview: enumerate → select → render (C-016)."""

    def __init__(self, *, tree_loader: Callable[[Path, Optional[str]], Any]) -> None:
        self._tree_loader = tree_loader

    def navigate(
        self,
        *,
        source_path: Path,
        focus_short_id: NodeId,
        selector: Union[str, Sequence[int], None],
        session_id: Optional[str] = None,
        config: Optional[PreviewSelectorConfig] = None,
        text_mode: PreviewTextMode = PreviewTextMode.ANNOTATED,
    ) -> PreviewNavigationResult:
        cfg = config or PreviewSelectorConfig()
        tree = self._tree_loader(source_path, session_id)
        max_sid = compute_max_short_id_in_tree(tree)
        try:
            children = self._enumerate_children(tree, focus_short_id)
        except UnknownNodeIdError as exc:
            raise PreviewNavigationError(str(exc)) from exc
        parsed = PreviewSelector.parse(selector)
        try:
            selected = parsed.apply(children)
        except PreviewSelectorError:
            raise
        format_key = format_key_from_extension(source_path.suffix)
        blocks = [
            self._render_block(
                block,
                format_key=format_key,
                config=cfg,
                text_mode=text_mode,
                source_path=source_path,
                max_short_id=max_sid,
            )
            for block in selected
        ]
        envelope_dict = {
            "focus_short_id": int(focus_short_id),
            "blocks": [
                {
                    "short_id": int(b.short_id),
                    "type_label": b.type_label,
                    "attribute_summary": b.attribute_summary,
                    "text_excerpt": b.text_excerpt,
                    "render_mode": b.render_mode.value,
                    "line_span": b.line_span,
                }
                for b in blocks
            ],
        }
        serialized = json.dumps(envelope_dict, ensure_ascii=False, indent=2)
        paginated = paginate_envelope(serialized, cfg.max_chars)
        return PreviewNavigationResult(
            focus_short_id=focus_short_id,
            blocks=blocks,
            serialized_envelope=paginated,
        )

    def _enumerate_children(self, tree: Any, focus_short_id: NodeId) -> List[Any]:
        _, by_short_id, children_by_parent = _build_indexes(tree)
        focus = by_short_id.get(focus_short_id)
        if focus is None:
            raise PreviewNavigationError(f"unknown short_id: {focus_short_id!r}")
        effective = _effective_focus_node(focus, by_short_id)
        direct = list(children_by_parent.get(effective.short_id, []))
        return _expand_indented_blocks(direct, children_by_parent)

    def _render_block(
        self,
        block: Any,
        *,
        format_key: str,
        config: PreviewSelectorConfig,
        text_mode: PreviewTextMode,
        source_path: Path,
        max_short_id: int,
    ) -> PreviewBlockRecord:
        del source_path  # reserved for consumer wiring
        kind = str(getattr(block, "kind", "") or "")
        content = str(getattr(block, "content", "") or "")
        attrs = getattr(block, "attributes", None) or {}

        if format_key == "python":
            content = strip_legacy_python_identity_comments(content)
        if format_key == "json":
            content = normalize_json_for_line_count(content)

        line_span = compute_line_span(content)
        render_mode = PreviewSelector.decide_render_mode(
            format_key=format_key,
            line_span=line_span,
            config=config,
        )

        if (
            text_mode == PreviewTextMode.STRUCTURAL
            or render_mode == PreviewRenderMode.DRILLDOWN
        ):
            start = attrs.get("start_line", "?")
            end = attrs.get("end_line", "?")
            excerpt = f"{kind} L{start}-{end}"
        elif render_mode == PreviewRenderMode.INLINE and text_mode in (
            PreviewTextMode.ANNOTATED,
            PreviewTextMode.FULL_TEXT,
        ):
            line_map = _line_to_short_id_for_block(block, content)
            excerpt = apply_line_id_prefixes(
                content,
                line_map,
                mode=text_mode,
                max_short_id=max_short_id,
            )
        else:
            excerpt = content

        return PreviewBlockRecord(
            short_id=block.short_id,
            type_label=kind,
            attribute_summary=_attribute_summary(attrs),
            text_excerpt=excerpt,
            render_mode=render_mode,
            line_span=line_span,
        )


def _iter_all_nodes(tree: Any) -> Sequence[Any]:
    if hasattr(tree, "all_nodes"):
        result = tree.all_nodes()
        return list(result) if not isinstance(result, list) else result
    if hasattr(tree, "nodes"):
        nodes = tree.nodes
        return list(nodes) if not isinstance(nodes, list) else nodes
    raise TypeError("tree must expose all_nodes() or nodes")


def _build_indexes(
    tree: Any,
) -> tuple[List[Any], Dict[NodeId, Any], Dict[Optional[NodeId], List[Any]]]:
    nodes = list(_iter_all_nodes(tree))
    by_short_id: Dict[NodeId, Any] = {}
    children_by_parent: Dict[Optional[NodeId], List[Any]] = {}
    for node in nodes:
        sid = getattr(node, "short_id", None)
        if isinstance(sid, int):
            by_short_id[NodeId(sid)] = node
        parent = getattr(node, "parent_short_id", None)
        children_by_parent.setdefault(parent, []).append(node)
    return nodes, by_short_id, children_by_parent


def _effective_focus_node(focus: Any, by_short_id: Dict[NodeId, Any]) -> Any:
    kind = str(getattr(focus, "kind", "") or "")
    if kind in _CONTAINER_KINDS:
        return focus
    if kind not in _SCALAR_KINDS:
        return focus
    current = focus
    while True:
        parent_sid = getattr(current, "parent_short_id", None)
        if parent_sid is None:
            break
        parent = by_short_id.get(parent_sid)
        if parent is None:
            break
        parent_kind = str(getattr(parent, "kind", "") or "")
        if parent_kind in _CONTAINER_KINDS:
            return parent
        current = parent
    return focus


def _expand_indented_blocks(
    direct_children: Sequence[Any],
    children_by_parent: Dict[Optional[NodeId], List[Any]],
) -> List[Any]:
    result: List[Any] = []
    for child in direct_children:
        if getattr(child, "kind", None) == INDENTED_BLOCK_KIND:
            sid = getattr(child, "short_id", None)
            grandchildren = list(children_by_parent.get(sid, []))
            result.extend(grandchildren)
        else:
            result.append(child)
    return result


def _line_to_short_id_for_block(block: Any, content: str) -> Dict[int, NodeId]:
    sid = block.short_id
    attrs = getattr(block, "attributes", None) or {}
    start = attrs.get("start_line")
    end = attrs.get("end_line")
    mapping: Dict[int, NodeId] = {}
    if isinstance(start, int) and isinstance(end, int) and start >= 1 and end >= start:
        for line_no in range(start, end + 1):
            mapping[line_no] = sid
        return mapping
    line_count = compute_line_span(content) or 1
    for i in range(1, line_count + 1):
        mapping[i] = sid
    return mapping


def _attribute_summary(attrs: Mapping[str, Any]) -> str:
    if not attrs:
        return ""
    parts: List[str] = []
    for key in sorted(attrs):
        if str(key).startswith("_"):
            continue
        parts.append(f"{key}={attrs[key]!r}")
    return ", ".join(parts)
