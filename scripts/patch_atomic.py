"""Patch atomic.py: replace .node_id with .stable_id for cst_node_id= assignments."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/database/files/atomic.py'
content = open(path).read()
before = content

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
count = content.count('stable_id,')
print(f'Patched OK: {count} stable_id occurrences written')
