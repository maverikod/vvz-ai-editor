import subprocess
# Commands modified this session that have metadata() methods
files = [
    # FTS fix - not commands, internal modules
    'ai_editor/core/database_client/client_api_files.py',
    'ai_editor/core/database/entities.py',
    'ai_editor/core/database/files/crud.py',
    'ai_editor/commands/compose_cst_db.py',
    # include_code feature
    'ai_editor/core/cst_tree/tree_finder.py',
    'ai_editor/commands/cst_find_node_command.py',
]
for f in files:
    r = subprocess.run(
        ['grep', '-n', 'def metadata\|def get_schema\|class.*Command',
         f'/home/vasilyvz/projects/tools/ai_editor/{f}'],
        capture_output=True, text=True
    )
    hits = r.stdout.strip()
    print(f'\n=== {f} ===')
    print(hits or '(no metadata/schema/Command)')
