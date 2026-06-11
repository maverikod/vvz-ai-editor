import pathlib

ROOT = pathlib.Path('/home/vasilyvz/projects/tools/ai_editor/ai_editor')
total = 0
for f in ROOT.rglob('*.py'):
    src = f.read_text(encoding='utf-8')
    lines = src.splitlines(keepends=True)
    cleaned = [l for l in lines if not l.strip().startswith('# @node-id:')]
    if len(cleaned) != len(lines):
        f.write_text(''.join(cleaned), encoding='utf-8')
        n = len(lines) - len(cleaned)
        print(f'Stripped {n} lines from {f.relative_to(ROOT)}')
        total += n
print(f'Done. Total stripped: {total}')
