"""Check deleted column DEFAULT."""
import pathlib

f = pathlib.Path(
    "/home/vasilyvz/projects/tools/ai_editor"
    "/ai_editor/core/database/schema_definition_tables_core.py"
)
lines = f.read_text().splitlines()
for line_no in (118, 157):
    print(f'--- context around line {line_no} ---')
    for i in range(line_no - 3, line_no + 5):
        print(f"{i+1}: {lines[i]}")
