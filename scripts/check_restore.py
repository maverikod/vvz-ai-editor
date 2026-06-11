"""Debug: load CST tree — stable ids live in sibling ``<source>.py.tree``, not in ``.py``."""

import sys
from pathlib import Path

sys.path.insert(0, "/home/vasilyvz/projects/tools/ai_editor")

from ai_editor.core.cst_tree import load_file_to_tree
from ai_editor.tree.sibling_convention import sibling_tree_path

TEST_FILE = "/home/vasilyvz/projects/tools/cst_mcp_sandbox_20260501/mcp_cst_workspace/test_inline_ids.py"

print("=== LOADING TREE ===")
tree = load_file_to_tree(TEST_FILE)
print(f"tree_id: {tree.tree_id}")
print(f"metadata_map size: {len(tree.metadata_map)}")
py = Path(TEST_FILE)
sc = sibling_tree_path(py.resolve())
print(f"sidecar path: {sc} exists={sc.is_file()}")
inline_hits = [
    i + 1 for i, l in enumerate(tree.module.code.splitlines()) if "@node-id" in l
]
print(f"Lines with @node-id in module.code: {inline_hits}")
