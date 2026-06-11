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
content = content.replace(anchor, anchor + norm_additions)

# 2. Add ON CONFLICT blocks in _adapt_sqlite_dml_for_postgres before the final "return s"
conflict_blocks = '''
    if norm == _CLASSES_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO classes "
            "(file_id, name, line, end_line, cst_node_id, docstring, bases) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (file_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "docstring = EXCLUDED.docstring, "
            "bases = EXCLUDED.bases"
        )
    if norm == _METHODS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO methods "
            "(class_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (class_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "args = EXCLUDED.args, "
            "docstring = EXCLUDED.docstring"
        )
    if norm == _FUNCTIONS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO functions "
            "(file_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (file_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "args = EXCLUDED.args, "
            "docstring = EXCLUDED.docstring"
        )
    return s
'''

old_return = '    return s\n'
if content.count(old_return) != 1:
    print(f'ERROR: found {content.count(old_return)} occurrences of return s in adapt function')
    sys.exit(1)
content = content.replace(old_return, conflict_blocks)

if content == before:
    print('ERROR: nothing changed')
    sys.exit(1)

open(path, 'w').write(content)
print('Patched OK — classes/methods/functions ON CONFLICT DO UPDATE added')
