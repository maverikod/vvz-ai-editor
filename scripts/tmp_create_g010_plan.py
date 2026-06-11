import os

base = '/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-12-universal-file-preview'

os.makedirs(f'{base}/G-010-python-node-visualizer', exist_ok=True)
for t in ['T-901-full-text-threshold', 'T-902-module-renderer', 'T-903-node-renderer', 'T-904-block-integration']:
    os.makedirs(f'{base}/G-010-python-node-visualizer/{t}', exist_ok=True)

g010 = 'step_id: G-010\nname: Python node visualizer\ndescription: >\n  Add a NodeVisualizer component to PythonFileHandler that renders any\n  node from CSTTree into a structured human-readable text preview.\n  Four rendering modes: module-level overview, class structure,\n  function/method body first-level, and full-text fallback for small files.\n  No changes to the public command schema or response envelope shape.\nconcepts:\n  - C-016\n  - C-022\n  - C-023\n  - C-003\n  - C-008\nrelations:\n  - {from_concept: C-022, to_concept: C-016, type: extends}\n  - {from_concept: C-022, to_concept: C-003, type: uses}\n  - {from_concept: C-022, to_concept: C-023, type: consumes}\n  - {from_concept: C-022, to_concept: C-008, type: implements}\nsource_ranges:\n  - {start: 26, end: 31}\n  - {start: 123, end: 142}\ndepends_on:\n  - G-001\n  - G-002\n  - G-003\n  - G-004\ntactical_steps:\n  - T-901\n  - T-902\n  - T-903\n  - T-904\nstatus: draft\n'

t901 = 'step_id: T-901\nparent_global_step: G-010\nname: Full-text threshold in PreviewBudget\ndescription: >\n  Add full_text_max_lines field to PreviewBudget dataclass and wire it\n  into UniversalFilePreviewCommand.get_schema() and validate_params().\n  Default value 200. When a Python file has fewer lines than this threshold,\n  PythonFileHandler.open_root returns the entire file as a single text block.\nconcepts:\n  - C-023\n  - C-013\n  - C-001\ninputs:\n  - {name: budget_py, type: file, description: budget.py}\n  - {name: command_py, type: file, description: universal_file_preview_command.py}\noutputs:\n  - {name: budget_py, type: file, description: PreviewBudget with full_text_max_lines}\n  - {name: command_py, type: file, description: schema and validate_params updated}\natomic_steps: []\nstatus: draft\n'

t902 = 'step_id: T-902\nparent_global_step: G-010\nname: Module-level renderer\ndescription: >\n  Create python_visualizer.py with render_module(tree, budget) function.\n  Returns text: file docstring, imports (stable_id + range + type),\n  constants, class signatures + docstrings + method signatures + docstrings,\n  module-level function signatures + docstrings.\nconcepts:\n  - C-022\n  - C-016\n  - C-009\ninputs:\n  - {name: tree, type: CSTTree, description: loaded CSTTree}\n  - {name: budget, type: PreviewBudget, description: with full_text_max_lines}\noutputs:\n  - {name: python_visualizer_py, type: file, description: new module with render_module}\natomic_steps: []\nstatus: draft\n'

t903 = 'step_id: T-903\nparent_global_step: G-010\nname: Node renderer\ndescription: >\n  Add render_node(tree, stable_id) to python_visualizer.py.\n  FunctionDef/AsyncFunctionDef: signature + docstring + body first-level\n  (compound stmts collapsed with stable_id + range + ...).\n  ClassDef: signature + docstring + method signatures + docstrings.\n  Compound stmts (If/For/While/Try/With): first line + stable_id + range + ...\nconcepts:\n  - C-022\n  - C-009\n  - C-016\ninputs:\n  - {name: python_visualizer_py, type: file, description: module from T-902}\n  - {name: stable_id, type: str, description: stable_id of target node}\noutputs:\n  - {name: python_visualizer_py, type: file, description: extended with render_node}\natomic_steps: []\nstatus: draft\n'

t904 = 'step_id: T-904\nparent_global_step: G-010\nname: Wire visualizer into PythonFileHandler block rendering\ndescription: >\n  Modify PythonFileHandler.open_root to use render_module for file overview.\n  Modify _metadata_children_to_nodes to put rendered text into Block.summary["text"].\n  Modify resolve_node_ref to call render_node and return in Block.summary["text"].\n  Add optional text field to Block dataclass alongside summary dict.\nconcepts:\n  - C-022\n  - C-016\n  - C-005\n  - C-008\ninputs:\n  - {name: python_visualizer_py, type: file, description: from T-902 and T-903}\n  - {name: python_handler_py, type: file, description: handlers/python_handler.py}\n  - {name: models_py, type: file, description: models.py}\noutputs:\n  - {name: python_handler_py, type: file, description: wired to visualizer}\n  - {name: models_py, type: file, description: Block with text field}\natomic_steps: []\nstatus: draft\n'

with open(f'{base}/G-010-python-node-visualizer/README.yaml', 'w') as f:
    f.write(g010)
with open(f'{base}/G-010-python-node-visualizer/T-901-full-text-threshold/README.yaml', 'w') as f:
    f.write(t901)
with open(f'{base}/G-010-python-node-visualizer/T-902-module-renderer/README.yaml', 'w') as f:
    f.write(t902)
with open(f'{base}/G-010-python-node-visualizer/T-903-node-renderer/README.yaml', 'w') as f:
    f.write(t903)
with open(f'{base}/G-010-python-node-visualizer/T-904-block-integration/README.yaml', 'w') as f:
    f.write(t904)

print('Done: G-010 + T-901..T-904 created')
