# Fix Task — tree-temp YAML serializer collapses a single-element list into a mapping

Component: code_analysis — universal_file_edit tree-temp pipeline
Primary file: code_analysis/commands/universal_file_edit/tree_temp_edit_nodes.py
Severity: medium (silent data-shape corruption; no exception raised)
Scope guard: YAML handler ONLY. JSON and text formats MUST remain byte-for-byte unchanged.
Status: open

## 1. Summary

When `universal_file_edit` writes a list that contains EXACTLY ONE element into a
YAML (tree-temp) document — via a `replace` or `insert` operation whose `value`
is that one-element list — the committed YAML renders the field as a MAPPING
instead of a one-element SEQUENCE.

Wrong (current behaviour):

    source_ranges:
      start: 1336
      end: 1353

Correct (expected):

    source_ranges:
    - start: 1336
      end: 1353

The field type silently changes from list[dict] to dict. Consumers that iterate
the field then read a single merged mapping instead of a list. Lists of two or
more elements are unaffected, which is why the defect is easy to miss.

## 2. Reproduction

1. `universal_file_open` a `.yaml` file (format_group = tree-temp).
2. `universal_file_edit` with one replace whose value is a one-element list of dicts:
   {"type": "replace", "json_pointer": "/source_ranges", "value": [{"start": 1336, "end": 1353}]}
3. `universal_file_write` write_mode=preview, then write_mode=commit.
4. Inspect committed YAML: `/source_ranges` is emitted as a mapping (start/end indented
   under the key) rather than a one-item block sequence (`- start:` form).

The same defect occurs for a top-level one-element list and for insert operations
whose value is a one-element list. A one-element list of scalars (e.g. ["x"]) is also
affected: it serialises as a bare scalar instead of a one-item sequence.

## 3. Root cause

Two helpers in `tree_temp_edit_nodes.py`:

`_value_to_tree_roots(handler_id, value)`
  - JSON branch: `if isinstance(value, (dict, list)): parse_json_source(json.dumps(value))`.
    The JSON parser (`core/tree_temp/json_source_parser.py`, `parse_document`) wraps a
    top-level `[...]` in a SINGLE `array` TreeNode and returns `[arr]` — so a one-element
    JSON list yields exactly one root of type `array`. JSON is therefore IMMUNE.
  - YAML branch: `yaml.safe_dump(value, ...)` then `parse_yaml_source(dumped)`.
    `parse_yaml_source` returns ONE ROOT PER top-level sequence element. For a list of
    one element it returns a single root that IS THAT ELEMENT (type object/scalar). The
    `array` wrapper is lost.

`_value_to_single_node(handler_id, value)`
  - `roots = _value_to_tree_roots(...); if len(roots) == 1: return roots[0]` — returns the
    bare element node; otherwise wraps multiple roots in an `array` node.
  - Net effect: a one-element list → single object/scalar node (WRONG); a list of >=2
    elements → array node (CORRECT). `replace` then copies the wrong `type` onto the target
    via `_merge_payload_keep_identity`, so the field changes shape.

The defect is that array-vs-object identity is inferred from the YAML round-trip text
(which is ambiguous for N=1) instead of from the original Python `value`.

## 4. Required fix (YAML branch only)

Decide the container shape from the Python `value` BEFORE/INSTEAD OF relying on the
YAML text round-trip, mirroring what the JSON branch already does.

Constraints:
- Touch ONLY the YAML path. Do NOT modify the JSON branch of `_value_to_tree_roots`,
  `_json_scalar_tree_node`, the JSON parser, or any text-format code.
- `_value_to_single_node` must return exactly one node whose `type` matches the Python value:
    - `list`  -> TreeNode(type="array", children=[one node per element]) — including the
      single-element and empty-list cases.
    - `dict`  -> TreeNode(type="object", children=[...]).
    - scalar  -> the corresponding scalar TreeNode.
- Element/child nodes must continue to round-trip through the existing YAML parser so that
  nested comments/ordering/scalar typing stay identical to today for the >=2-element case.
- Preserve existing public signatures of `_value_to_tree_roots`, `_value_to_single_node`,
  `apply_single_tree_temp_mutation`. No call-site changes elsewhere.
- Empty list `[]` -> empty `array` node; empty dict `{}` -> empty `object` node (parity
  with JSON).

Implementation hint (non-binding): in `_value_to_single_node`, branch on the Python value
first — if `isinstance(value, list)`, build an `array` TreeNode whose children are
`_value_to_single_node(handler_id, element)` for each element (regenerating stable ids is
already handled downstream by `_regenerate_stable_ids` at the insert/replace site); if
`isinstance(value, dict)`, build an `object` node similarly; otherwise fall back to the
existing single-root path. Keep the YAML text round-trip for individual scalar/leaf values
so scalar typing is unchanged. Do not change the JSON branch — it is already correct.

## 5. Non-regression guard for other formats (MANDATORY)

The patch must be proven NOT to affect JSON or text formats:
- No diff in any JSON-handler code path. Add/keep a JSON regression test asserting a
  one-element JSON list stays an `array` (it already does; lock it in).
- Text format group has no involvement; assert no edits to text apply/serialize modules.
- Run the full existing tree-temp suite (see section 7) and confirm zero changed assertions
  for JSON and YAML >=2-element cases.

## 6. Acceptance criteria

A. `replace` of `/k` with value `[{"a": 1}]` on a YAML doc commits:
       k:
       - a: 1
   (one-item block sequence), not a mapping.
B. `replace` with value `["x"]` commits a one-item sequence of a scalar, not a bare scalar.
C. `insert` with value `[{"a": 1}]` into a YAML mapping key commits a one-item sequence.
D. `replace` with value `[{"a":1},{"b":2}]` (>=2 elements) is unchanged from today.
E. JSON: `replace` of `/k` with `[{"a":1}]` still commits a one-element JSON array — unchanged.
F. A top-level one-element list round-trips as a one-item YAML sequence.
G. Empty list `[]` round-trips as an empty YAML sequence; empty dict `{}` as an empty mapping.

## 7. Tests to add / run

Add:
- tests/test_tree_temp_source_parser_yaml.py: a `test_yaml_sequence_single_element_under_array_root`
  mirroring the existing `test_yaml_sequence_three_elements_under_array_root` but with N=1,
  asserting the produced node is `type=="array"` with exactly one child.
- tests/test_tree_temp_universal_yaml_edit_write_close.py: integration tests for criteria
  A, B, C, F, G (open -> edit replace/insert one-element list -> write preview+commit ->
  assert committed YAML text contains the `- ` sequence marker and the field parses back to
  a list).
- tests/test_tree_temp_universal_json_edit_write_close.py: a regression test for criterion E
  (one-element JSON list stays an array) if not already covered.

Run (must stay green):
- tests/test_tree_temp_universal_yaml_edit_write_close.py
- tests/test_tree_temp_universal_json_edit_write_close.py
- tests/test_tree_temp_source_parser_yaml.py
- tests/test_tree_temp_source_parser_json.py
- tests/test_tree_temp_tree_node_model.py (esp. test_root_encoding_single_object_vs_root_array_contract)
- tests/test_tree_temp_serializer_yaml_roundtrip.py
- tests/test_tree_temp_serializer_json_roundtrip.py
- tests/test_tree_temp_edit_session_lifecycle.py

## 8. Out of scope

- No change to JSON parser/serializer or scalar handling.
- No change to text-format apply/serialize/close paths.
- No change to public command schemas or metadata.
- No new dependencies.
