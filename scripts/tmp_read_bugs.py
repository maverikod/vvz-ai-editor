files = [
    '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/indexing_worker_pkg/processing.py',
    '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/worker_project_activity.py',
    '/home/vasilyvz/projects/tools/ai_editor/ai_editor/commands/run_project_script_command.py',
]
for fpath in files:
    print(f'\n===== {fpath} =====')
    with open(fpath) as f:
        src = f.read()
    print(src)
