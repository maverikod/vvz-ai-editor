import os

base = '/home/vasilyvz/projects/tools/ai_editor/docs/plans/2026-05-12-universal-file-preview'

os.makedirs(f'{base}/G-011-python-handler-refactor', exist_ok=True)
for t in ['T-1001-drop-dead-code', 'T-1002-open-root-rewrite', 'T-1003-block-model-text-field', 'T-1004-smoke-test']:
    os.makedirs(f'{base}/G-011-python-handler-refactor/{t}', exist_ok=True)

g011 = 'step_id: G-011\nname: PythonFileHandler refactor\ndescription: >\n  Refactor PythonFileHandler and its helpers after G-010 visualizer is in place.\n  Goals: (1) remove dead code paths left from pre-visualizer era (_cst_statements_to_nodes,\n  _cst_node_to_node, _classify_cst_node, _find_by_stable_id — kept only if used elsewhere);\n  (2) rewrite _metadata_children_to_nodes to correctly enumerate module-level children\n  using outline_nodes depth=1 from metadata_map instead of iterating children_ids;\n  (3) rewrite open_root to call render_module and return structured text block;\n  (4) add text field to Block model and wire it through response serialization;\n  (5) smoke-test the full round-trip with a real Python file.\nconcepts:\n  - C-016\n  - C-003\n  - C-005\n  - C-022\nrelations:\n  - {from_concept: C-016, to_concept: C-003, type: extends}\n  - {from_concept: C-016, to_concept: C-022, type: uses}\ndepends_on:\n  - G-010\ntactical_steps:\n  - T-1001\n  - T-1002\n  - T-1003\n  - T-1004\nstatus: draft\n'

t1001 = 'step_id: T-1001\nparent_global_step: G-011\nname: Drop dead code from python_handler.py\ndescription: >\n  Remove functions no longer needed after G-010 visualizer is wired:\n  _cst_statements_to_nodes, _cst_node_to_node, _classify_cst_node, _find_by_stable_id.\n  Verify none are imported elsewhere before deletion.\n  Remove dead imports that become unused after deletion.\nconcepts:\n  - C-016\ninputs:\n  - {name: python_handler_py, type: file, description: handlers/python_handler.py}\noutputs:\n  - {name: python_handler_py, type: file, description: cleaned file without dead functions}\natomic_steps: []\nstatus: draft\n'

t1002 = 'step_id: T-1002\nparent_global_step: G-011\nname: Rewrite open_root and _metadata_children_to_nodes\ndescription: >\n  Rewrite open_root: always call cst_load_file, then call render_module(tree, budget)\n  from python_visualizer, return single text Block with the rendered string.\n  Rewrite _metadata_children_to_nodes: iterate metadata_map filtering by depth==parent_depth+1\n  and parent_id==parent_node_id, skip whitespace kinds, return Nodes with correct stable_id.\n  This fixes the root cause of SimpleStatementLine showing instead of real types.\nconcepts:\n  - C-016\n  - C-022\ninputs:\n  - {name: python_handler_py, type: file, description: handlers/python_handler.py after T-1001}\n  - {name: python_visualizer_py, type: file, description: python_visualizer.py from G-010}\noutputs:\n  - {name: python_handler_py, type: file, description: rewritten open_root and helper}\natomic_steps: []\nstatus: draft\n'

t1003 = 'step_id: T-1003\nparent_global_step: G-011\nname: Add text field to Block model\ndescription: >\n  Add optional text: str | None = None field to Block dataclass in models.py.\n  Update ResponseEnvelope serialization in response.py to include text field\n  in block output when non-None. Update block_handlers.py tree_node handler\n  to pass rendered text through instead of building child_count summary.\nconcepts:\n  - C-005\n  - C-008\n  - C-012\ninputs:\n  - {name: models_py, type: file, description: universal_file_preview/models.py}\n  - {name: response_py, type: file, description: universal_file_preview/response.py}\n  - {name: block_handlers_py, type: file, description: universal_file_preview/block_handlers.py}\noutputs:\n  - {name: models_py, type: file, description: Block with text field}\n  - {name: response_py, type: file, description: serialization updated}\n  - {name: block_handlers_py, type: file, description: tree_node handler updated}\natomic_steps: []\nstatus: draft\n'

t1004 = 'step_id: T-1004\nparent_global_step: G-011\nname: Smoke test full round-trip\ndescription: >\n  Call universal_file_preview on three test cases and verify output:\n  (1) small file (<200 lines) — expect full text fallback;\n  (2) large file (>200 lines) without node_ref — expect module overview with imports, classes, functions;\n  (3) large file with node_ref pointing to a FunctionDef — expect signature + docstring + first-level body.\n  Fix any issues found before marking G-011 done.\nconcepts:\n  - C-001\n  - C-016\ninputs:\n  - {name: server, type: runtime, description: MCP server running with updated code}\noutputs:\n  - {name: test_results, type: verification, description: all three cases produce expected text preview}\natomic_steps: []\nstatus: draft\n'

with open(f'{base}/G-011-python-handler-refactor/README.yaml', 'w') as f:
    f.write(g011)
with open(f'{base}/G-011-python-handler-refactor/T-1001-drop-dead-code/README.yaml', 'w') as f:
    f.write(t1001)
with open(f'{base}/G-011-python-handler-refactor/T-1002-open-root-rewrite/README.yaml', 'w') as f:
    f.write(t1002)
with open(f'{base}/G-011-python-handler-refactor/T-1003-block-model-text-field/README.yaml', 'w') as f:
    f.write(t1003)
with open(f'{base}/G-011-python-handler-refactor/T-1004-smoke-test/README.yaml', 'w') as f:
    f.write(t1004)

print('Done: G-011 + T-1001..T-1004 created')
