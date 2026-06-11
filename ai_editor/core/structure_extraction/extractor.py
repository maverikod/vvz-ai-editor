"""
Extract preview-compatible structural blocks without DB or vectorization.

Stable disk Python ids require a persisted CST sidecar (same path as indexer/preview).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    _line_for_json_pointer,
)
from ai_editor.commands.universal_file_preview.handlers.markdown_handler import (
    _iter_md_block_tokens,
    _md_block_node_ref,
)
from ai_editor.commands.universal_file_preview.handlers.yaml_handler import (
    _line_for_yaml_pointer,
)
from ai_editor.core.cst_tree.models import TreeNodeMetadata
from ai_editor.core.json_tree.tree_builder import build_tree_from_data
from ai_editor.core.structure_extraction.format_registry import (
    JSON_SUFFIX,
    MD_SUFFIXES,
    PY_SUFFIXES,
    TEXT_PLAIN_SUFFIXES,
    YAML_SUFFIXES,
    format_group_for_suffix,
)
from ai_editor.core.structure_extraction.models import (
    PreviewRef,
    SourceKind,
    StructureBlock,
    StructureDocument,
    StructureWarning,
)
from ai_editor.core.structure_extraction.stable_tree import (
    TreeResolutionStats,
    resolve_python_metadata_stable,
)
from ai_editor.core.yaml_tree.tree_builder import build_yaml_tree_from_data

_TRIVIAL_NODE_TYPES = frozenset(
    {
        "SimpleWhitespace",
        "TrailingWhitespace",
        "Newline",
        "EmptyLine",
        "Comment",
        "Whitespace",
    }
)

_PREFERRED_SIDECAR_KINDS = frozenset(
    {"method", "function", "class", "stmt", "smallstmt", "module"}
)


def extract_structure(
    *,
    file_path: str,
    content: str,
    format_hint: str | None = None,
    source: str = "disk",
    session_id: str | None = None,
    include_text: bool = True,
    ensure_persisted_tree: bool = True,
    stable_ids_required: bool = True,
    tree_stats: TreeResolutionStats | None = None,
    preview_file_path: str | None = None,
) -> StructureDocument:
    """
    Build structural blocks using the same rules as indexer/preview.

    No database writes, embeddings, or chunker calls.
    """
    source_kind: SourceKind = "draft_session" if source == "draft_session" else "disk"
    content_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    suffix = Path(file_path).suffix.lower()
    format_group = format_hint or format_group_for_suffix(suffix)
    warnings: List[StructureWarning] = []
    blocks: List[StructureBlock] = []
    ids_stable = False

    try:
        if suffix in PY_SUFFIXES:
            blocks, py_warnings, ids_stable = _extract_python_blocks(
                file_path,
                content,
                include_text=include_text,
                source=source_kind,
                session_id=session_id,
                ensure_persisted_tree=ensure_persisted_tree,
                stable_ids_required=stable_ids_required,
                tree_stats=tree_stats,
            )
            warnings.extend(py_warnings)
        elif suffix == JSON_SUFFIX:
            blocks, ids_stable = _extract_json_blocks(
                file_path, content, include_text=include_text
            )
        elif suffix in YAML_SUFFIXES:
            blocks, ids_stable = _extract_yaml_blocks(
                file_path, content, include_text=include_text
            )
        elif suffix in MD_SUFFIXES:
            blocks, ids_stable = _extract_markdown_blocks(
                file_path, content, include_text=include_text
            )
        elif suffix in TEXT_PLAIN_SUFFIXES:
            blocks, ids_stable = _extract_plain_text_blocks(
                content,
                include_text=include_text,
                stable_ids_required=stable_ids_required,
            )
        else:
            warnings.append(
                StructureWarning(
                    code="UNSUPPORTED_FORMAT",
                    message=f"No structure extractor for suffix {suffix!r}",
                    file_path=file_path,
                )
            )
    except Exception as exc:
        warnings.append(
            StructureWarning(
                code="EXTRACT_FAILED",
                message=str(exc),
                file_path=file_path,
            )
        )

    preview_path = preview_file_path or file_path
    for block in blocks:
        if block.node_ref is not None:
            block.preview = PreviewRef(
                file_path=preview_path,
                node_ref=block.node_ref,
                selector=block.path or block.node_ref,
                session_id=session_id,
            )

    return StructureDocument(
        file_path=file_path,
        format_group=format_group,
        source=source_kind,
        session_id=session_id,
        content_sha256=content_sha,
        blocks=blocks,
        warnings=warnings,
        ids_stable=ids_stable and bool(blocks),
        preview_file_path=preview_path,
    )


def find_smallest_block_containing_line(
    document: StructureDocument,
    line_number: int,
) -> StructureBlock | None:
    """Return the smallest block whose line range contains ``line_number`` (1-based)."""
    candidates = [
        b for b in document.blocks if b.start_line <= line_number <= b.end_line
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda b: (b.end_line - b.start_line, b.start_line),
    )


def _preview_block(
    *,
    block_id: str | None,
    node_type: str,
    start_line: int,
    end_line: int,
    node_ref: Optional[str] = None,
    name: Optional[str] = None,
    qualname: Optional[str] = None,
    path: Optional[str] = None,
    text: Optional[str] = None,
    start_col: Optional[int] = None,
    end_col: Optional[int] = None,
) -> StructureBlock:
    return StructureBlock(
        block_id=block_id or "",
        node_ref=node_ref,
        node_type=node_type,
        name=name,
        qualname=qualname,
        path=path,
        start_line=start_line,
        end_line=end_line,
        start_col=start_col,
        end_col=end_col,
        text=text,
    )


def _extract_python_blocks(
    file_path: str,
    content: str,
    *,
    include_text: bool,
    source: SourceKind,
    session_id: Optional[str],
    ensure_persisted_tree: bool,
    stable_ids_required: bool,
    tree_stats: TreeResolutionStats | None,
) -> tuple[List[StructureBlock], List[StructureWarning], bool]:
    abs_path = Path(file_path).resolve()
    meta, warnings, stats = resolve_python_metadata_stable(
        abs_path,
        content,
        source=source,
        session_id=session_id,
        ensure_persisted_tree=ensure_persisted_tree and stable_ids_required,
    )
    if tree_stats is not None:
        tree_stats.files_requiring_tree_check += stats.files_requiring_tree_check
        tree_stats.valid_trees_reused += stats.valid_trees_reused
        tree_stats.stale_trees_rebuilt += stats.stale_trees_rebuilt
        tree_stats.missing_trees_created += stats.missing_trees_created

    if not meta:
        return [], warnings, False

    lines = content.splitlines()
    blocks: List[StructureBlock] = []
    for node_meta in meta.values():
        if node_meta.type in _TRIVIAL_NODE_TYPES:
            continue
        if node_meta.kind not in _PREFERRED_SIDECAR_KINDS:
            continue
        snippet = None
        if include_text and lines:
            start = max(1, node_meta.start_line)
            end = min(len(lines), node_meta.end_line)
            snippet = "\n".join(lines[start - 1 : end])
        stable = node_meta.stable_id
        blocks.append(
            _preview_block(
                block_id=stable,
                node_ref=stable,
                node_type=node_meta.type,
                name=node_meta.name,
                qualname=node_meta.qualname,
                start_line=node_meta.start_line,
                end_line=node_meta.end_line,
                start_col=node_meta.start_col,
                end_col=node_meta.end_col,
                text=snippet,
            )
        )
    return blocks, warnings, True


def _line_map_from_pointers(
    source: str,
    metadata_map: dict,
    line_for_pointer,
    pointer_attr: str,
) -> dict[int, tuple[str, str, str, str]]:
    lines = source.splitlines()
    if not lines:
        return {}
    starts: list[tuple[int, str, str, str, str]] = []
    for meta in metadata_map.values():
        pointer = getattr(meta, pointer_attr, "") or ""
        start = getattr(meta, "start_line", None)
        if start is None:
            start = line_for_pointer(lines, pointer)
        if start is None:
            continue
        name = getattr(meta, "key", None) or getattr(meta, "kind", "")
        starts.append((start, pointer, meta.kind, str(name) if name else "", pointer))
    starts.sort(key=lambda item: item[0])
    if not starts:
        return {}
    line_map: dict[int, tuple[str, str, str, str]] = {}
    for line_num in range(1, len(lines) + 1):
        best: tuple[str, str, str, str] | None = None
        best_start = -1
        for start, pointer, kind, name, _ in starts:
            if start <= line_num and start >= best_start:
                best_start = start
                best = (pointer, kind, name, pointer)
        if best is not None:
            line_map[line_num] = best
    return line_map


def _extract_json_blocks(
    file_path: str, content: str, *, include_text: bool
) -> tuple[List[StructureBlock], bool]:
    data = json.loads(content)
    tree = build_tree_from_data(str(Path(file_path).resolve()), data)
    line_map = _line_map_from_pointers(
        content, tree.metadata_map, _line_for_json_pointer, "json_pointer"
    )
    return (
        _blocks_from_pointer_line_map(file_path, content, line_map, include_text),
        True,
    )


def _extract_yaml_blocks(
    file_path: str, content: str, *, include_text: bool
) -> tuple[List[StructureBlock], bool]:
    import yaml

    data = yaml.safe_load(content)
    tree = build_yaml_tree_from_data(str(Path(file_path).resolve()), data)
    line_map = _line_map_from_pointers(
        content, tree.metadata_map, _line_for_yaml_pointer, "yaml_pointer"
    )
    return (
        _blocks_from_pointer_line_map(file_path, content, line_map, include_text),
        True,
    )


def _blocks_from_pointer_line_map(
    file_path: str,
    content: str,
    line_map: dict[int, tuple[str, str, str, str]],
    include_text: bool,
) -> List[StructureBlock]:
    if not line_map:
        return []
    by_pointer: dict[str, tuple[int, int, str, str]] = {}
    lines = content.splitlines()
    for line_num, (pointer, kind, name, _) in line_map.items():
        prev = by_pointer.get(pointer)
        if prev is None:
            by_pointer[pointer] = (line_num, line_num, kind, name)
        else:
            by_pointer[pointer] = (
                min(prev[0], line_num),
                max(prev[1], line_num),
                kind,
                name,
            )
    blocks: List[StructureBlock] = []
    for pointer, (start, end, kind, name) in by_pointer.items():
        snippet = None
        if include_text and lines:
            snippet = "\n".join(lines[start - 1 : end])
        blocks.append(
            _preview_block(
                block_id=pointer,
                node_ref=pointer,
                path=pointer,
                node_type=kind,
                name=name or None,
                start_line=start,
                end_line=end,
                text=snippet,
            )
        )
    return blocks


def _extract_markdown_blocks(
    file_path: str, content: str, *, include_text: bool
) -> tuple[List[StructureBlock], bool]:
    from markdown_it import MarkdownIt

    tokens = list(_iter_md_block_tokens(MarkdownIt().parse(content)))
    resolved = str(Path(file_path).resolve())
    lines = content.splitlines()
    blocks: List[StructureBlock] = []
    for token in tokens:
        if token.map is None:
            continue
        start, end = token.map
        start_line = start + 1
        end_line = end
        node_ref = _md_block_node_ref(resolved, token)
        snippet = None
        if include_text and lines:
            snippet = "\n".join(lines[start:end])
        blocks.append(
            _preview_block(
                block_id=node_ref,
                node_ref=node_ref,
                node_type=token.type,
                start_line=start_line,
                end_line=end_line,
                text=snippet,
            )
        )
    return blocks, True


def _extract_plain_text_blocks(
    content: str,
    *,
    include_text: bool,
    stable_ids_required: bool,
) -> tuple[List[StructureBlock], bool]:
    """Per-line stable node_ref (zero-based index) for text preview handler."""
    lines = content.splitlines() or [""]
    blocks: List[StructureBlock] = []
    for i, _line in enumerate(lines, start=1):
        node_ref = str(i - 1) if stable_ids_required else None
        blocks.append(
            _preview_block(
                block_id=node_ref or f"line:{i}",
                node_ref=node_ref,
                node_type="line",
                start_line=i,
                end_line=i,
                text=_line if include_text else None,
            )
        )
    return blocks, stable_ids_required
