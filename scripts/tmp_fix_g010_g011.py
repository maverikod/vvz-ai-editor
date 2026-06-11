import yaml

base = '/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-12-universal-file-preview'

# Fix G-010
g010_path = f'{base}/G-010-python-node-visualizer/README.yaml'
with open(g010_path, 'r') as f:
    g010 = yaml.safe_load(f)

# Fix source_ranges: sections 15 and 16 of source_spec
# Section 15 starts at line 259 (after original 258 lines + blank line)
# Use line numbers from new source_spec (310 total lines)
# Section 15: lines 259-295, Section 16: lines 296-307
g010['source_ranges'] = [
    {'start': 259, 'end': 295},
    {'start': 296, 'end': 307},
]

# Fix relations: remove C-022 consumes C-023 (wrong - C-016 consumes C-023 in spec)
# Keep: C-022 extends C-016, C-022 uses C-003, C-022 implements C-008
g010['relations'] = [
    {'from_concept': 'C-022', 'to_concept': 'C-016', 'type': 'extends'},
    {'from_concept': 'C-022', 'to_concept': 'C-003', 'type': 'uses'},
    {'from_concept': 'C-022', 'to_concept': 'C-008', 'type': 'implements'},
    {'from_concept': 'C-016', 'to_concept': 'C-023', 'type': 'consumes'},
]

with open(g010_path, 'w') as f:
    yaml.dump(g010, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
print('G-010 updated')

# Fix G-011
g011_path = f'{base}/G-011-python-handler-refactor/README.yaml'
with open(g011_path, 'r') as f:
    g011 = yaml.safe_load(f)

# Add source_ranges (was missing)
# G-011 covers: Python handler (section 3 lines 25-33), child preview rule (section 7 lines 107-142),
# structured text rendering (section 15 lines 259-295)
g011['source_ranges'] = [
    {'start': 25, 'end': 33},
    {'start': 107, 'end': 142},
    {'start': 259, 'end': 307},
]

# Relations: C-016 uses C-022 already correct; add C-016 consumes C-023
existing_rels = g011.get('relations', [])
existing_keys = {(r['from_concept'], r['to_concept']) for r in existing_rels}
if ('C-016', 'C-023') not in existing_keys:
    g011['relations'].append({'from_concept': 'C-016', 'to_concept': 'C-023', 'type': 'consumes'})

# Add C-023 to concepts if not present
if 'C-023' not in g011.get('concepts', []):
    g011['concepts'].append('C-023')

with open(g011_path, 'w') as f:
    yaml.dump(g011, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
print('G-011 updated')
print('G-011 concepts:', g011['concepts'])
print('G-011 source_ranges:', g011['source_ranges'])
print('G-011 relations:', g011['relations'])
