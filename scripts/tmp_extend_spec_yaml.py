import yaml

path = '/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-12-universal-file-preview/spec.yaml'

with open(path, 'r') as f:
    spec = yaml.safe_load(f)

# Verify C-022 and C-023 don't already exist
existing_ids = [c['concept_id'] for c in spec['concepts']]
print('Existing concept IDs:', existing_ids)
assert 'C-022' not in existing_ids, 'C-022 already exists'
assert 'C-023' not in existing_ids, 'C-023 already exists'

# Add C-022: PythonNodeRenderer
c022 = {
    'concept_id': 'C-022',
    'name': 'PythonNodeRenderer',
    'definition': 'Component that renders a CSTTree node into a structured text block suitable for direct AI model consumption, following the rules in source_spec sections 15 and 16.',
    'properties': [
        'renders Module as: docstring + top-level entities (imports, constants, classes, functions) each prefixed with stable_id and line range',
        'renders ClassDef as: class signature + docstring + method signatures + method docstrings',
        'renders FunctionDef/AsyncFunctionDef as: signature + docstring + first-level body (compound stmts collapsed to first line + stable_id + range + ...)',
        'renders compound stmts (If/For/While/Try/With/Match) as focus: first line + stable_id + range + first-level body with same collapse rule',
        'output placed in text field of block summary',
        'when text is present, it takes precedence over generic type/name/attributes/child_count fields',
    ],
    'source_ranges': [{'start': 259, 'end': 295}],
}

# Add C-023: FullTextThreshold
c023 = {
    'concept_id': 'C-023',
    'name': 'FullTextThreshold',
    'definition': 'A numeric budget cap that triggers full-file text fallback in the Python handler when the file line count is below the threshold.',
    'properties': [
        'parameter name: full_text_max_lines',
        'default value: 200 lines',
        'when file lines < full_text_max_lines: return entire file source as single text block',
        'when value is 0: full-text fallback disabled',
        'part of PreviewBudget alongside preview_lines and value_preview_len',
    ],
    'source_ranges': [{'start': 296, 'end': 307}],
}

spec['concepts'].append(c022)
spec['concepts'].append(c023)

# Add relations
new_relations = [
    {'from_concept': 'C-022', 'to_concept': 'C-016', 'type': 'extends'},
    {'from_concept': 'C-022', 'to_concept': 'C-003', 'type': 'uses'},
    {'from_concept': 'C-022', 'to_concept': 'C-008', 'type': 'implements'},
    {'from_concept': 'C-016', 'to_concept': 'C-022', 'type': 'uses'},
    {'from_concept': 'C-023', 'to_concept': 'C-013', 'type': 'extends'},
    {'from_concept': 'C-016', 'to_concept': 'C-023', 'type': 'consumes'},
]

for r in new_relations:
    spec['relations'].append(r)

with open(path, 'w') as f:
    yaml.dump(spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print('Done. Concepts count:', len(spec['concepts']))
print('Relations count:', len(spec['relations']))
print('Last concept:', spec['concepts'][-1]['concept_id'])
