"""Check PostgreSQL schema for functions/classes/methods table constraints."""
import sys
sys.path.insert(0, '/home/vasilyvz/projects/tools/ai_editor')

from ai_editor.core.database_driver_pkg.drivers.postgres_run import (
    _norm_sql_one_line,
    _adapt_sqlite_dml_for_postgres,
    _FUNCTIONS_INSERT_OR_REPLACE_NORM,
    _CLASSES_INSERT_OR_REPLACE_NORM,
    _METHODS_INSERT_OR_REPLACE_NORM,
)

# Test that norms match the actual SQL
test_sql_func = (
    'INSERT OR REPLACE INTO functions '
    '(file_id, name, line, end_line, cst_node_id, args, docstring) '
    'VALUES (?, ?, ?, ?, ?, ?, ?)'
)
test_sql_class = (
    'INSERT OR REPLACE INTO classes '
    '(file_id, name, line, end_line, cst_node_id, docstring, bases) '
    'VALUES (?, ?, ?, ?, ?, ?, ?)'
)
test_sql_method = (
    'INSERT OR REPLACE INTO methods '
    '(class_id, name, line, end_line, cst_node_id, args, docstring) '
    'VALUES (?, ?, ?, ?, ?, ?, ?)'
)

print('--- Norm match check ---')
print(f'functions norm matches: {_norm_sql_one_line(test_sql_func) == _FUNCTIONS_INSERT_OR_REPLACE_NORM}')
print(f'classes norm matches:   {_norm_sql_one_line(test_sql_class) == _CLASSES_INSERT_OR_REPLACE_NORM}')
print(f'methods norm matches:   {_norm_sql_one_line(test_sql_method) == _METHODS_INSERT_OR_REPLACE_NORM}')
print()
print('--- Adapted SQL for functions ---')
print(_adapt_sqlite_dml_for_postgres(test_sql_func))
print()
print('--- Adapted SQL for classes ---')
print(_adapt_sqlite_dml_for_postgres(test_sql_class))
