path = '/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-12-universal-file-preview/source_spec.md'

with open(path, 'r') as f:
    content = f.read()

marker = '<!-- non-binding -->'
assert marker in content, 'Marker not found'

new_sections = (
    '## 15. Python handler structured text rendering\n'
    '\n'
    'The Python file handler produces a structured text rendering of any node,\n'
    'suitable for direct consumption by AI models. This rendering replaces the\n'
    'generic JSON child-count summary for Python `tree_node` nodes with a\n'
    'human-readable text block.\n'
    '\n'
    'The rendering follows these rules by node type:\n'
    '\n'
    '- **Module (file root):** The rendering includes the module docstring, followed\n'
    '  by one line per top-level entity: import lines with their stable identifier\n'
    '  and line range, constant assignments, class signatures with class docstrings\n'
    '  and method signatures with method docstrings, and module-level function\n'
    '  signatures with docstrings. Each entity is prefixed with its stable\n'
    '  identifier in brackets and its line range.\n'
    '\n'
    '- **ClassDef:** The rendering includes the class signature and docstring,\n'
    '  followed by each method\'s signature and docstring. Method bodies are not\n'
    '  included.\n'
    '\n'
    '- **FunctionDef / AsyncFunctionDef:** The rendering includes the full function\n'
    '  signature, full docstring, and the first-level body. Compound statements\n'
    '  at the first level (`if`, `for`, `while`, `try`, `with`, `match`) are\n'
    '  collapsed: only the first line of the compound statement is shown, followed\n'
    '  by `...`, prefixed with the statement\'s stable identifier and line range.\n'
    '  Simple statements at the first level are shown in full.\n'
    '\n'
    '- **Compound statements (If, For, While, Try, With, Match) as focus node:**\n'
    '  The same first-level rendering applies: the statement itself is shown with\n'
    '  its stable identifier, line range, and first line, followed by its\n'
    '  first-level body with the same collapse rule.\n'
    '\n'
    'The stable identifier and line range prefix format is:\n'
    '`[stable_id] Lstart-end` for multi-line nodes, `[stable_id] Lline` for\n'
    'single-line nodes.\n'
    '\n'
    'This structured text is returned in the `text` field of the block summary.\n'
    'When `text` is present, the caller should use it instead of the generic\n'
    '`type`, `name`, `attributes`, `child_count` fields for display purposes.\n'
    '\n'
    '## 16. Python handler full-text threshold\n'
    '\n'
    'The Python file handler accepts a `full_text_max_lines` parameter as part of\n'
    'the preview budget. When the target Python file has fewer lines than this\n'
    'threshold, the handler returns the entire file source as a single text block\n'
    'instead of the structured rendering described in section 15. This allows\n'
    'callers to read small files in one step without navigating the tree structure.\n'
    '\n'
    'The default value of `full_text_max_lines` is 200 lines. The parameter is\n'
    'optional; when omitted, the default applies. A value of 0 disables the\n'
    'full-text fallback entirely.\n'
    '\n'
)

new_content = content.replace(marker, new_sections + marker)

with open(path, 'w') as f:
    f.write(new_content)

with open(path, 'r') as f:
    lines = f.readlines()
print(f'Done. Total lines: {len(lines)}')
print(f'Section 15 present: {chr(35) + chr(35) + " 15." in new_content}')
print(f'Section 16 present: {chr(35) + chr(35) + " 16." in new_content}')
print(f'Original marker preserved: {marker in new_content}')
