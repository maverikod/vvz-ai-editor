"""Patch build_load_response to resolve stable_id in selectors."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/cst_load_file_helpers.py'
content = open(path).read()
before = content

# Fix 1: list selector - lookup by stable_id instead of only node_id
old1 = '''        elif isinstance(selector, list):
            for node_id in selector:
                if isinstance(node_id, str) and node_id in tree.metadata_map:
                    selected_metas.append(tree.metadata_map[node_id])'''
new1 = '''        elif isinstance(selector, list):
            for node_id in selector:
                if isinstance(node_id, str):
                    if node_id in tree.metadata_map:
                        selected_metas.append(tree.metadata_map[node_id])
                    else:
                        meta = tree.find_by_stable_id(node_id)
                        if meta:
                            selected_metas.append(meta)'''

# Fix 2: dict selector with node_ids - same
old2 = '''                raw_ids = selector.get("node_ids")
                if isinstance(raw_ids, list):
                    for node_id in raw_ids:
                        if isinstance(node_id, str) and node_id in tree.metadata_map:
                            selected_metas.append(tree.metadata_map[node_id])'''
new2 = '''                raw_ids = selector.get("node_ids")
                if isinstance(raw_ids, list):
                    for node_id in raw_ids:
                        if isinstance(node_id, str):
                            if node_id in tree.metadata_map:
                                selected_metas.append(tree.metadata_map[node_id])
                            else:
                                meta = tree.find_by_stable_id(node_id)
                                if meta:
                                    selected_metas.append(meta)'''

content = content.replace(old1, new1, 1)
content = content.replace(old2, new2, 1)

if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)

open(path, 'w').write(content)
print('Patched OK')
