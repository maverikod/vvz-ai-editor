"""Check worker SQL adaptation directly."""
import sys
sys.path.insert(0, '/home/vasilyvz/projects/tools/ai_editor')

from ai_editor.core.database_driver_pkg.drivers.postgres_run import (
    _adapt_sqlite_dml_for_postgres,
    _FUNCTIONS_INSERT_OR_REPLACE_NORM,
    _norm_sql_one_line,
)

# The exact SQL from client_api_files.py after patch
sql = (
    'INSERT OR REPLACE INTO functions '
    '(file_id, name, line, end_line, cst_node_id, args, docstring) '
    'VALUES (?, ?, ?, ?, ?, ?, ?)'
)

adapted = _adapt_sqlite_dml_for_postgres(sql)
print('ADAPTED:', adapted)
print()
print('Has ON CONFLICT:', 'ON CONFLICT' in adapted)
print('Has cst_node_id:', 'cst_node_id' in adapted)

# Also check the actual norm stored
print()
print('NORM:', repr(_FUNCTIONS_INSERT_OR_REPLACE_NORM))
print('SQL NORM:', repr(_norm_sql_one_line(sql)))
print('MATCH:', _norm_sql_one_line(sql) == _FUNCTIONS_INSERT_OR_REPLACE_NORM)
