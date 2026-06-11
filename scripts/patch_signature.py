"""Patch _build_signature to skip @node-id lines."""
import sys
path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/cst_tree/skeleton.py'
content = open(path).read()
before = content
old = '        if not stripped and not header_lines:\n            continue\n        header_lines.append(stripped)'
new = '        # Skip inline stable_id comments\n        if stripped.strip().startswith("# @node-id:"):\n            continue\n        if not stripped and not header_lines:\n            continue\n        header_lines.append(stripped)'
content = content.replace(old, new, 1)
if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)
open(path, 'w').write(content)
print('Patched OK')
