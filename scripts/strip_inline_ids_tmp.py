import pathlib

f = pathlib.Path('/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/cst_find_node_command.py')
src = f.read_text()
lines = src.splitlines(keepends=True)
cleaned = [l for l in lines if not l.strip().startswith('# @node-id:')]
f.write_text(''.join(cleaned))
print('Stripped', len(lines) - len(cleaned), 'node-id lines')
