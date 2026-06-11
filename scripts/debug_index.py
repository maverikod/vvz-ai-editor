"""Debug indexing: directly index test_inline_ids.py and check SQL."""
import sys, json
sys.path.insert(0, '/home/vasilyvz/projects/tools/ai_editor')

# Patch to intercept SQL
from ai_editor.core.database_driver_pkg.drivers import postgres_run as pr
orig_adapt = pr._adapt_sqlite_dml_for_postgres
# @node-id: 593c35df-4472-49e4-800c-13265ca5ba5d

def patched_adapt(sql):
    result = orig_adapt(sql)
    if 'functions' in sql.lower() or 'classes' in sql.lower() or 'methods' in sql.lower():
        print(f'[SQL ADAPT] IN:  {sql[:80]}')
        print(f'[SQL ADAPT] OUT: {result[:120]}')
    return result

pr._adapt_sqlite_dml_for_postgres = patched_adapt

# Now run a minimal index
from ai_editor.core.database_client.client_api_files import ClientApiFiles
from ai_editor.core.database_driver_pkg.db_factory import create_db_connection

# Get DB connection for sandbox project
from ai_editor.core.config import get_settings
settings = get_settings()
print(f'DB type: {settings.db_type}')
print(f'DB URL: {str(settings.db_url)[:50]}')

# Try to call add_function directly
try:
    db = create_db_connection()
    file_id = 1  # dummy
    print('Testing add_function call...')
    # We can't do this without a real file_id but we can check the SQL
    sql = (
        'INSERT OR REPLACE INTO functions '
        '(file_id, name, line, end_line, cst_node_id, args, docstring) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)'
    )
    adapted = pr._adapt_sqlite_dml_for_postgres(sql)
    print(f'Adapted: {adapted[:150]}')
except Exception as e:
    print(f'Error: {e}')
