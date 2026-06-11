"""Patch selected_nodes block."""
path = 'ai_editor/commands/cst_load_file_helpers.py'
with open(path) as f:
    src = f.read()

old = (
    '        selected_with_code = []\n'
    '        for meta in selected_metas:\n'
    '            with_code = get_node_metadata(tree.tree_id, meta.node_id, include_code=True)\n'
    '            selected_with_code.append(\n'
    '                with_code.to_dict() if with_code else meta.to_dict()\n'
    '            )\n'
    '        data["selected_nodes"] = selected_with_code'
)

new = (
    '        selected_with_code = []\n'
    '        for meta in selected_metas:\n'
    '            entry = meta.to_dict()\n'
    '            # Apply declarative rules: function/method/class -> skeleton;\n'
    '            # other node kinds -> include full code inline.\n'
    '            if meta.kind in {"function", "method", "class"}:\n'
    '                overview_text, outline = build_node_declarative_overview(\n'
    '                    tree, meta.node_id\n'
    '                )\n'
    '                entry["declarative"] = overview_text\n'
    '                entry["outline_nodes"] = outline\n'
    '            else:\n'
    '                with_code = get_node_metadata(\n'
    '                    tree.tree_id, meta.node_id, include_code=True\n'
    '                )\n'
    '                if with_code:\n'
    '                    entry = with_code.to_dict()\n'
    '            selected_with_code.append(entry)\n'
    '        data["selected_nodes"] = selected_with_code'
)

if old not in src:
    print('OLD NOT FOUND')
    idx = src.find('selected_with_code = []')
    print(repr(src[idx:idx+400]))
else:
    new_src = src.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(new_src)
    print('OK lines:', new_src.count(chr(10)) + 1)
