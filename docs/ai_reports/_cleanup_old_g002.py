import shutil, pathlib
p = pathlib.Path('/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-16-universal-file-edit/G-002-session-and-draft-model')
if p.exists():
    shutil.rmtree(p)
    print('deleted')
else:
    print('not found')
