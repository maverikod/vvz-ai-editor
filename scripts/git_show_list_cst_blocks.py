import subprocess
from pathlib import Path

ROOT = Path('/home/vasilyvz/projects/tools/ai_editor')
FILE = 'ai_editor/commands/list_cst_blocks_command.py'

# Что изменилось в последнем коммите
print('=== git show de54580 -- list_cst_blocks_command.py ===')
r = subprocess.run(
    ['git', 'show', 'de54580', '--', FILE],
    capture_output=True, text=True, cwd=ROOT
)
print(r.stdout[:4000] or '(no output)')

# Полная история изменений построчно
print('\n=== git log -p --follow -- list_cst_blocks_command.py (last 3 commits) ===')
r2 = subprocess.run(
    ['git', 'log', '-p', '-3', '--follow', '--', FILE],
    capture_output=True, text=True, cwd=ROOT
)
print(r2.stdout[:6000] or '(no output)')
