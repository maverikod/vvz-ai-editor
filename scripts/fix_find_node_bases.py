import pathlib

path = pathlib.Path('/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/cst_find_node_command.py')
src = path.read_text(encoding='utf-8')
old = 'class CSTFindNodeCommand:'
new = 'class CSTFindNodeCommand(BaseMCPCommand):'
if old in src:
    path.write_text(src.replace(old, new, 1), encoding='utf-8')
    print('Done: replaced class declaration')
else:
    print('ERROR: pattern not found')
