#!/usr/bin/env python3
"""Profile universal_file_preview hot path for one Python file."""

from __future__ import annotations

import time
from pathlib import Path

PROJECT_ROOT = Path("/home/vasilyvz/projects/tools/vast_srv")
REL_FILE = "ai_admin/core/app_factory/app_factory_impl.py"
ABS_FILE = PROJECT_ROOT / REL_FILE


def _sec(start: float) -> float:
    return time.perf_counter() - start


def _report(label: str, elapsed: float) -> None:
    print(f"  {label:48s} {elapsed:7.3f}s")


def main() -> None:
    if not ABS_FILE.is_file():
        raise SystemExit(f"missing file: {ABS_FILE}")

    lines = len(ABS_FILE.read_text(encoding="utf-8").splitlines())
    size_kb = ABS_FILE.stat().st_size / 1024
    print(f"File: {REL_FILE}")
    print(f"  lines={lines}  size={size_kb:.1f} KiB\n")

    from ai_editor.commands.universal_file_preview.budget import PreviewBudget
    from ai_editor.commands.universal_file_preview.marked_tree_loader import (
        make_preview_tree_loader,
        resolve_format_handler,
    )
    from ai_editor.commands.universal_file_preview.marked_tree_navigation import (
        _enrich_focus_for_root_view,
        navigate_marked_tree,
    )
    from ai_editor.core.cst_tree.tree_builder import (
        create_tree_from_code,
        load_file_to_tree,
    )
    from ai_editor.core.tree_lifecycle.lifecycle import TreeLifecycle
    from ai_editor.tree.handler_registry import HandlerRegistry

    content = ABS_FILE.read_text(encoding="utf-8")
    budget = PreviewBudget(preview_lines=20, value_preview_len=120, full_text_max_lines=200)

    print("=== Micro-benchmarks (isolated) ===")

    t0 = time.perf_counter()
    import libcst as cst

    module = cst.parse_module(content)
    _report("libcst.parse_module", _sec(t0))

    t0 = time.perf_counter()
    handler = resolve_format_handler(ABS_FILE)
    marked = handler.mark(content)
    _report("PythonFormatHandler.mark", _sec(t0))

    t0 = time.perf_counter()
    create_tree_from_code(str(ABS_FILE), content, persist_sidecar=False, register_in_memory=False)
    _report("create_tree_from_code (no sidecar)", _sec(t0))

    t0 = time.perf_counter()
    load_file_to_tree(str(ABS_FILE))
    _report("load_file_to_tree (legacy CST + .py.tree)", _sec(t0))

    t0 = time.perf_counter()
    handler.parse_content(ABS_FILE, content)
    _report("handler.parse_content", _sec(t0))

    t0 = time.perf_counter()
    TreeLifecycle.from_path(project_root=PROJECT_ROOT, file_path=REL_FILE)
    _report("TreeLifecycle.from_path", _sec(t0))

    print("\n=== End-to-end marked-tree preview path ===")

    t0 = time.perf_counter()
    result = navigate_marked_tree(
        {
            "project_root": PROJECT_ROOT,
            "rel_file_path": REL_FILE,
            "file_path": str(ABS_FILE),
            "node_ref": None,
            "selector": None,
            "session_id": None,
        },
        budget,
    )
    total = _sec(t0)
    _report("navigate_marked_tree TOTAL", total)

    if hasattr(result, "focus_node"):
        focus_text = (result.focus_node.attributes or {}).get("text", "")
        print(f"\n  focus.text chars={len(focus_text)}  blocks={len(result.selected_blocks)}")
    else:
        print(f"\n  error: {result}")

    print("\n=== Loader breakdown (manual steps) ===")
    loader = make_preview_tree_loader(
        project_root=PROJECT_ROOT,
        rel_file_path=REL_FILE,
        preview_abs_path=ABS_FILE,
        bound_session_id=None,
    )

    t0 = time.perf_counter()
    TreeLifecycle.from_path(project_root=PROJECT_ROOT, file_path=REL_FILE)
    t_lifecycle = _sec(t0)

    t0 = time.perf_counter()
    tree = loader(ABS_FILE, None)
    t_loader = _sec(t0)

    from ai_editor.commands.universal_file_preview.marked_tree_navigation import (
        _build_indexes,
        _tree_node_to_preview_node,
        parse_focus_short_id,
    )
    from ai_editor.tree.preview_navigation import PreviewNavigation
    from ai_editor.tree.preview_selector import PreviewSelector, PreviewSelectorConfig
    from ai_editor.tree.sibling_convention import PreviewTextMode
    from ai_editor.commands.universal_file_preview.marked_tree_navigation import (
        _root_view_block_set,
        compute_max_short_id_in_tree,
        format_key_from_extension,
    )

    focus_short_id = parse_focus_short_id(None, tree.nodes)
    format_key = format_key_from_extension(ABS_FILE.suffix)
    config = PreviewSelectorConfig(full_text_max_lines={format_key: budget.full_text_max_lines})
    navigation = PreviewNavigation(tree_loader=loader)
    max_short_id = compute_max_short_id_in_tree(tree)

    t0 = time.perf_counter()
    block_set = _root_view_block_set(tree, navigation, focus_short_id)
    t_blocks = _sec(t0)

    t0 = time.perf_counter()
    selected = PreviewSelector.parse(f"0:{budget.preview_lines}").apply(block_set)
    rendered = [
        navigation._render_block(
            block,
            format_key=format_key,
            config=config,
            text_mode=PreviewTextMode.ANNOTATED,
            source_path=ABS_FILE,
            max_short_id=max_short_id,
        )
        for block in selected
    ]
    t_render_blocks = _sec(t0)

    _, by_short_id, _ = _build_indexes(tree)
    focus_node = _tree_node_to_preview_node(by_short_id[focus_short_id])

    t0 = time.perf_counter()
    _enrich_focus_for_root_view(
        focus_node,
        tree=tree,
        source_text=content,
        format_key=format_key,
        budget=budget,
        config=config,
        preview_abs_path=ABS_FILE,
        max_short_id=max_short_id,
    )
    t_enrich = _sec(t0)

    _report("  TreeLifecycle.from_path (in loader)", t_lifecycle)
    _report("  loader() incl. parse_content", t_loader)
    _report("  _root_view_block_set", t_blocks)
    _report("  render selected blocks", t_render_blocks)
    _report("  _enrich_focus_for_root_view", t_enrich)
    print(f"  sum(steps)={t_lifecycle + t_loader + t_blocks + t_render_blocks + t_enrich:.3f}s")


if __name__ == "__main__":
    main()
