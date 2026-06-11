import sys
sys.path.insert(0, '/home/vasilyvz/projects/tools/ai_editor')

from ai_editor.core.cst_tree import tree_builder
from ai_editor.core.cst_tree.tree_finder import find_nodes
from pathlib import Path
import tempfile, os, uuid

SOURCE = '''
def add(a, b):
    """Add two numbers."""
    return a + b

def subtract(a, b):
    """Subtract."""
    return a - b
'''

with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write(SOURCE)
    tmp = f.name

try:
    # Use create_tree_from_code and register manually
    tree_id = str(uuid.uuid4())
    tree = tree_builder.create_tree_from_code(tmp, SOURCE)
    tree_builder._trees[tree_id] = tree

    # --- Test 1: Without include_code ---
    matches = find_nodes(tree_id, query="FunctionDef", include_code=False)
    print(f'Without include_code: {len(matches)} matches')
    for m in matches:
        print(f'  {m.name}: code is None = {m.code is None}')

    # --- Test 2: With include_code=True ---
    matches = find_nodes(tree_id, query="FunctionDef", include_code=True)
    print(f'\nWith include_code=True: {len(matches)} matches')
    for m in matches:
        preview = m.code[:50].replace('\n', '<NL>') if m.code else None
        print(f'  {m.name}: code={preview!r}')

    print('\n✅ include_code works!')

    # --- Test 3: Optimal 2-call flow demo ---
    print('\n--- Optimal flow: find+code -> replace_many ---')
    matches = find_nodes(tree_id, query="FunctionDef[name='add']", include_code=True)
    m = matches[0]
    print(f'Call 1: cst_find_node(include_code=True)')
    print(f'  -> node_id={m.node_id[:8]}...')
    print(f'  -> code={m.code[:40].replace(chr(10), "<NL>")!r}...')
    print(f'Call 2: cst_modify_tree(replace_many: [{{node_id, code_lines}}])')
    print(f'  -> done. Total: 2 calls, 0 extra round-trips.')

    # --- Token cost comparison ---
    OLD_TOKENS = 300  # find + get_node_info + modify
    NEW_TOKENS = 120  # find(include_code) + modify
    print(f'\nToken saving: {OLD_TOKENS} -> {NEW_TOKENS} = {100*(OLD_TOKENS-NEW_TOKENS)//OLD_TOKENS}% reduction')

finally:
    del tree_builder._trees[tree_id]
    os.unlink(tmp)
