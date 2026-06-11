"""Patch postgres_run.py: add ON CONFLICT DO UPDATE for classes/methods/functions."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/database_driver_pkg/drivers/postgres_run.py'
content = open(path).read()
before = content

# 1. Add norm constants after _CODE_CHUNKS_INSERT_OR_REPLACE_NORM line
norm_additions = '''
# Entity INSERT OR REPLACE norms (classes / methods / functions)
_CLASSES_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO classes "
    "(file_id, name, line, end_line, cst_node_id, docstring, bases) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_METHODS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO methods "
    "(class_id, name, line, end_line, cst_node_id, args, docstring) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_FUNCTIONS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO functions "
    "(file_id, name, line, end_line, cst_node_id, args, docstring) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
'''

anchor = '_CODE_CHUNKS_INSERT_OR_REPLACE_NORM = code_chunk_upsert_norm_for_postgres_adapter()'
if anchor not in content:
    print('ERROR: anchor not found')
    sys.exit(1)
content = content.replace(anchor, anchor + norm_additions, 1)

# 2. Replace the specific last return in _adapt_sqlite_dml_for_postgres
# The function ends with: ...updated_at\n        )\n    return s\n\n\ndef _sqlite
old_tail = '            "updated_at = EXCLUDED.updated_at"\n        )\n    return s\n'
new_tail = (
    '            "updated_at = EXCLUDED.updated_at"\n'
    '        )\n'
    '    if norm == _CLASSES_INSERT_OR_REPLACE_NORM:\n'
    '        return (\n'
    '            "INSERT INTO classes "\n'
    '            "(file_id, name, line, end_line, cst_node_id, docstring, bases) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?) "\n'
    '            "ON CONFLICT (file_id, name, line) DO UPDATE SET "\n'
    '            "end_line = EXCLUDED.end_line, "\n'
    '            "cst_node_id = EXCLUDED.cst_node_id, "\n'
    '            "docstring = EXCLUDED.docstring, "\n'
    '            "bases = EXCLUDED.bases"\n'
    '        )\n'
    '    if norm == _METHODS_INSERT_OR_REPLACE_NORM:\n'
    '        return (\n'
    '            "INSERT INTO methods "\n'
    '            "(class_id, name, line, end_line, cst_node_id, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?) "\n'
    '            "ON CONFLICT (class_id, name, line) DO UPDATE SET "\n'
    '            "end_line = EXCLUDED.end_line, "\n'
    '            "cst_node_id = EXCLUDED.cst_node_id, "\n'
    '            "args = EXCLUDED.args, "\n'
    '            "docstring = EXCLUDED.docstring"\n'
    '        )\n'
    '    if norm == _FUNCTIONS_INSERT_OR_REPLACE_NORM:\n'
    '        return (\n'
    '            "INSERT INTO functions "\n'
    '            "(file_id, name, line, end_line, cst_node_id, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?) "\n'
    '            "ON CONFLICT (file_id, name, line) DO UPDATE SET "\n'
    '            "end_line = EXCLUDED.end_line, "\n'
    '            "cst_node_id = EXCLUDED.cst_node_id, "\n'
    '            "args = EXCLUDED.args, "\n'
    '            "docstring = EXCLUDED.docstring"\n'
    '        )\n'
    '    return s\n'
)

if old_tail not in content:
    print('ERROR: tail anchor not found')
    sys.exit(1)

content = content.replace(old_tail, new_tail, 1)

if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)

open(path, 'w').write(content)
print('Patched OK — ON CONFLICT DO UPDATE for classes/methods/functions added')
