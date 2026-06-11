# Step 06 -- query_cst empty diff investigation

## Status: PARTIALLY DONE -- needs core/cst_module investigation

## Findings

File: code_analysis/commands/query_cst_command.py
File: code_analysis/commands/query_cst_handler.py

execute node_id: 716ed060-ddc7-46ba-990f-aed13881461c (line 164)
run_replace_flow node_id: 3eb92f75-3216-44dd-891b-e13dc453c468 (line 334)

diff is computed correctly in run_replace_flow (line 366-382):
  diff = unified_diff(source, new_source, file_path)
  "diff": diff
  "replaced": stats.get("replaced", 0)

unified_diff imported from: ..core.cst_module
apply_replace_ops imported from: ..core.cst_module

## Root cause hypothesis

Problem is in core/cst_module.py:
- unified_diff may return empty string when source == new_source
  (no real change) but replaced counter is still 1
- OR apply_replace_ops returns replaced=1 even when no actual change made

## Next step

Read core/cst_module.py:
- find unified_diff implementation
- find apply_replace_ops implementation
- check if replaced counter is incremented even when old==new

File to read: code_analysis/core/cst_module.py (or similar path)
