"""Debug: detect legacy ``# @node-id:`` lines and show text-strip result."""

import sys

sys.path.insert(0, "/home/vasilyvz/projects/tools/ai_editor")

import libcst as cst

from ai_editor.core.cst_tree.node_stable_id import (
    strip_inline_node_id_lines_from_source,
)

TEST_FILE = "/home/vasilyvz/projects/tools/cst_mcp_sandbox_20260501/mcp_cst_workspace/test_inline_ids.py"

raw = open(TEST_FILE, encoding="utf-8").read()
lines_with_node_id = [i + 1 for i, l in enumerate(raw.splitlines()) if "@node-id" in l]
print("=== DISK STATE ===")
print(f"Total lines: {raw.count(chr(10)) + 1}")
print(f"Lines with @node-id: {lines_with_node_id}")

stripped = strip_inline_node_id_lines_from_source(raw)
lines_after = [i + 1 for i, l in enumerate(stripped.splitlines()) if "@node-id" in l]
print()
print("=== TEXT STRIP ===")
print(f"Lines with @node-id after strip: {lines_after}")
print("strip OK" if not lines_after else "strip FAILED")

# Parse stripped source (same as tree_builder load path)
module = cst.parse_module(stripped)
assert "@node-id" not in module.code
