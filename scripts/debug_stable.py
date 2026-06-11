"""Debug get_stable_id."""

import sys

sys.path.insert(0, "/home/vasilyvz/projects/tools/ai_editor")

from ai_editor.core.cst_tree.node_stable_id import get_stable_id
from ai_editor.core.cst_tree.node_id_markers import strip_persisted_node_ids
import libcst as cst

TEST_FILE = "/home/vasilyvz/projects/tools/cst_mcp_sandbox_20260501/mcp_cst_workspace/test_inline_ids.py"

raw = open(TEST_FILE).read()
print(f"File lines: {raw.count(chr(10))+1}")
lines_with_id = [i + 1 for i, l in enumerate(raw.splitlines()) if "@node-id" in l]
print(f"Lines with @node-id: {lines_with_id}")

# Simulate what old cst_load_file does
logical_source, persisted = strip_persisted_node_ids(raw)
module = cst.parse_module(logical_source)

print()
print("FunctionDef/ClassDef nodes and their stable_ids:")
for node in module.body:
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        name = node.name.value
        sid = get_stable_id(node)
        print(f"  {name}: stable_id={sid}")
    elif isinstance(node, cst.SimpleStatementLine):
        pass

# Also check class methods
for node in module.body:
    if isinstance(node, cst.ClassDef):
        for item in node.body.body:
            if isinstance(item, cst.FunctionDef):
                name = item.name.value
                sid = get_stable_id(item)
                print(f"  {node.name.value}.{name}: stable_id={sid}")
