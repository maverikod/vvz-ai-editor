<!--
Tactical task — parent global step: repair_cst_editing_for_server_only_vast_srv
-->

# Tactical Task: Repair CST leaf replace (server) for vast_srv workflow

## Purpose

Stop `cst_modify_tree` **replace** from promoting `Param` / `Name` targets to the enclosing `FunctionDef`, which caused unsafe whole-function replacement during server-only `vast_srv` Phase 1.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_editing_for_server_only_vast_srv.md`

## Scope

**Included:** `code_analysis` CST pipeline (`cst_modify_tree_helpers`, `tree_modifier_ops_*`, validation); pytest for command pipeline; MCP revalidation on `add_fallback_logic.py`.

**Excluded:** Direct edits to `test_data/vast_srv` outside MCP; `coder_auto`/`tester_auto` touching `vast_srv` files.

## Boundaries

- `vast_srv` changes only via **tester_ca** MCP.

## Dependencies

Blocked Phase 1 batch (git_auth_manager fix already done earlier).

## Parallelization note

Serial: code → restart/tests → MCP revalidation.

## Expected outcome

Leaf `Param`/`Name` replace preview scopes to signature only; interrupted `add_fallback_logic.py` fixes can be saved.

## Correction items

none

## Questions/escalation rule

Further fine-grained node types → escalate for parser/validation extensions.

---

## Specialist evidence

| Role | Outcome |
|------|---------|
| researcher_code | `_resolve_to_replaceable_node_id` promoted inner nodes to statement ancestor; `find_node_in_module_by_position` widened span. |
| coder_auto | Leaf path: no promotion for `Param`/`Name`; `find_leaf_node_in_module_by_position`; `parse_param_snippet`; `NodeReplacer` accepts leaf nodes; tests in `test_cst_modify_tree_command.py`. |
| tester_auto | Restart OK; **28** tests passed in `test_cst_modify_tree_command.py`; later restart after session crash **pid 669731**. |
| tester_ca | Preview **PASS** (diff only `self`→`file_path`); param rename **saved**; `replace_return` **template.format** fix **saved** after reload workaround; **flake8 4**, **mypy 2** remain (E265/E402/import order + mypy config/untyped). |

## File inventory (server code, coder_auto)

- `code_analysis/commands/cst_modify_tree_helpers.py`
- `code_analysis/core/cst_tree/tree_modifier_ops_parse.py`
- `code_analysis/core/cst_tree/tree_modifier_ops_find.py`
- `code_analysis/core/cst_tree/tree_modifier_ops_replace.py`
- `code_analysis/core/cst_tree/tree_modifier_validate.py`
- `code_analysis/core/cst_tree/tree_modifier_ops.py`
- `tests/test_cst_modify_tree_command.py`

## vast_srv (tester_ca only)

- `add_fallback_logic.py` — param rename + `replace_return` body pattern fix saved.

## Checkpoint

**CST editing:** Repaired and revalidated. **Phase 1 resume:** `add_fallback_logic.py` **advanced**; **next** bounded batch may target **E402/E265** and **mypy** noise without CST structural blocker.
