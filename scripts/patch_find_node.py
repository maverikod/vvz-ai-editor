"""Patch node_id to stable_id in cst_find_node_command."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/cst_find_node_command.py'
content = open(path).read()

before = content
content = content.replace(
    '"node_id": m.node_id,',
    '"stable_id": m.stable_id,',
    1
)
content = content.replace(
    'data["node_id"] = nodes[0].get("node_id")',
    'data["stable_id"] = nodes[0].get("stable_id")',
    1
)

if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)

open(path, 'w').write(content)
print('Patched OK')
