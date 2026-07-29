"""
Regression tests for bug 1db1038b: independent CST rebuilds of the same
session file must agree on freshly-minted identifiers.

``universal_file_search`` and ``universal_file_edit`` share one in-process
``EditSession`` (module-level ``_session_bundles`` registry) and one
in-process tree registry (module-level ``_trees`` in ``tree_builder.py``),
but each has its OWN fallback that rebuilds the CST from the on-disk draft
--- always with ``previous_metadata_map=None`` --- whenever
``get_tree(session.tree_id)`` returns ``None`` (e.g. the tree_id was evicted
by the 15-minute idle TTL cleanup, or no tree was ever registered yet):

* ``search_command.py`` -> ``_refresh_in_memory_cst_without_sidecar`` ->
  ``create_tree_from_code(..., persist_sidecar=False)``
* ``sidecar_cst_apply.py`` (``_run_sidecar_cst_batch_sync``) ->
  ``load_file_to_tree(...)``

Before the fix, every node without a persisted/carried identity got
``str(uuid.uuid4())`` for both ``node_id`` and ``stable_id``: two independent
rebuilds of byte-identical source at the same path minted unrelated random
identifiers, so a ``stable_id`` returned by a search response was rejected
(``STALE_NODE_ID``) by an edit call against the same unchanged session file.

Fix (strategy 2): fresh-mint identity is now deterministic --
``uuid.UUID(bytes=sha256(file_path|type|position)[:16], version=4)`` -- so any
id captured from one rebuild resolves in another independent rebuild of the
same file, as long as the file content has not changed in between.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.cst_tree.tree_builder import (
    create_tree_from_code,
    load_file_to_tree,
    remove_tree,
)


def test_independent_rebuilds_of_identical_source_agree_on_fresh_ids(
    tmp_path: Path,
) -> None:
    """Two unrelated, independent rebuilds of the same on-disk file (no
    sidecar, no previous_metadata_map -- exactly the search-fallback /
    edit-fallback shape) must mint identical node_id/stable_id per node.
    """
    path = tmp_path / "sample.py"
    source = "import os\n\nx = 1\n\n\ndef foo():\n    return 1\n"
    path.write_text(source, encoding="utf-8")

    # Build 1: mirrors search_command's _refresh_in_memory_cst_without_sidecar
    # (create_tree_from_code, persist_sidecar=False -- no .py.tree written).
    tree_a = create_tree_from_code(str(path), source, persist_sidecar=False)
    try:
        # Build 2: mirrors sidecar_cst_apply's edit-side fallback
        # (load_file_to_tree) after get_tree(session.tree_id) returned None.
        # No sidecar exists (build 1 didn't write one), so this also falls
        # through to the fresh-mint path with previous_metadata_map=None.
        tree_b = load_file_to_tree(str(path))
        try:
            assert tree_a.tree_id != tree_b.tree_id  # genuinely independent trees

            ids_from_build_1 = set()
            for meta in tree_a.metadata_map.values():
                ids_from_build_1.add(meta.node_id)
                ids_from_build_1.add(meta.stable_id)

            ids_in_build_2 = set()
            for meta in tree_b.metadata_map.values():
                ids_in_build_2.add(meta.node_id)
                ids_in_build_2.add(meta.stable_id)

            missing = ids_from_build_1 - ids_in_build_2
            assert not missing, (
                "identifiers minted in build 1 do not resolve in build 2 "
                f"(independent rebuild of identical source): {missing}"
            )

            # And the per-node identity actually matches (not just present
            # somewhere): same (type, position) node has the same node_id
            # and the same stable_id across both independent builds.
            by_position_a = {
                (m.type, m.start_line, m.start_col, m.end_line, m.end_col): m
                for m in tree_a.metadata_map.values()
            }
            by_position_b = {
                (m.type, m.start_line, m.start_col, m.end_line, m.end_col): m
                for m in tree_b.metadata_map.values()
            }
            assert set(by_position_a) == set(by_position_b)
            for key, meta_a in by_position_a.items():
                meta_b = by_position_b[key]
                assert meta_a.node_id == meta_b.node_id, key
                assert meta_a.stable_id == meta_b.stable_id, key
        finally:
            remove_tree(tree_b.tree_id)
    finally:
        remove_tree(tree_a.tree_id)


def test_fresh_mint_ids_differ_across_distinct_files_with_identical_content(
    tmp_path: Path,
) -> None:
    """Determinism must be keyed by file path too: two different files with
    byte-identical content must not collide on the same fresh-minted ids."""
    source = "x = 1\n"
    path_1 = tmp_path / "one.py"
    path_2 = tmp_path / "two.py"
    path_1.write_text(source, encoding="utf-8")
    path_2.write_text(source, encoding="utf-8")

    tree_1 = create_tree_from_code(str(path_1), source, persist_sidecar=False)
    tree_2 = create_tree_from_code(str(path_2), source, persist_sidecar=False)
    try:
        ids_1 = {m.node_id for m in tree_1.metadata_map.values()}
        ids_2 = {m.node_id for m in tree_2.metadata_map.values()}
        assert ids_1.isdisjoint(ids_2)
    finally:
        remove_tree(tree_1.tree_id)
        remove_tree(tree_2.tree_id)
