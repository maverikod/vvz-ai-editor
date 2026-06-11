import subprocess
import sys
import asyncio
from pathlib import Path

ROOT = Path('/home/vasilyvz/projects/tools/ai_editor')

# -- git log ----------------------------------------------------------------
print('=== git log -- ai_editor/commands/list_cst_blocks_command.py ===')
r = subprocess.run(
    ['git', 'log', '--oneline', '-15',
     '--', 'ai_editor/commands/list_cst_blocks_command.py'],
    capture_output=True, text=True, cwd=ROOT
)
print(r.stdout or '(no output)')
if r.stderr:
    print('STDERR:', r.stderr[:200])

# -- git diff HEAD --------------------------------------------------------
print('=== git diff HEAD -- list_cst_blocks_command.py ===')
r2 = subprocess.run(
    ['git', 'diff', 'HEAD', '--stat',
     '--', 'ai_editor/commands/list_cst_blocks_command.py'],
    capture_output=True, text=True, cwd=ROOT
)
print(r2.stdout or '(clean - no diff)')

# -- live test via MCP command class ------------------------------------
print('=== live execute test ===')
from ai_editor.commands.list_cst_blocks_command import ListCSTBlocksCommand
cmd = ListCSTBlocksCommand()

result = asyncio.run(cmd.execute(
    project_id='8772a086-688d-4198-a0c4-f03817cc0e6c',
    file_path='ai_editor/commands/list_cst_blocks_command.py',
))
print('result type:', type(result).__name__)
d = getattr(result, 'data', {})
print('success:', d.get('success'))
print('total_blocks:', d.get('total_blocks'))
blocks = d.get('blocks', [])
for b in blocks[:5]:
    print(f"  {b['kind']:10} {b['qualname']} [{b['start_line']}-{b['end_line']}]")
if len(blocks) > 5:
    print(f'  ... ({len(blocks)} total)')

# -- metadata check -------------------------------------------------------
print('=== metadata ===')
meta = ListCSTBlocksCommand.metadata()
print('name:', meta.get('name'))
print('category:', meta.get('category'))
print('description:', str(meta.get('description', ''))[:120])
params = meta.get('parameters', {})
print('params:', list(params.keys()))
