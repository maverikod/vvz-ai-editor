"""Patch index_entities to use stable_id instead of node_id for cst_node_id."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/update_indexes_entities.py'
content = open(path).read()
before = content

# Replace .node_id with .stable_id in three cst_node_id= assignments
content = content.replace(
    'cst_node_id=class_cst_node.node_id,',
    'cst_node_id=class_cst_node.stable_id,',
)
content = content.replace(
    'cst_node_id=method_cst_node.node_id,',
    'cst_node_id=method_cst_node.stable_id,',
)
content = content.replace(
    'cst_node_id=function_cst_node.node_id,',
    'cst_node_id=function_cst_node.stable_id,',
)

if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)

open(path, 'w').write(content)
print('Patched OK')
