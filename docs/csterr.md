# CST/MCP problems observed during `write_project_text_lines` hotfix attempt

## Context

Task: fix `code_analysis/commands/write_project_text_lines_command.py` so the command works only for plain text files and does not route markdown/text through Python AST indexing.

Intended source change:

```text
.md/.txt/.rst/.adoc -> allowed as plain text
.py/source/json/yaml/toml/unknown -> reject before write/backup/DB/index side effects
plain text success path -> do not call update_file_data_atomic_batch
```

Project rules required editing existing Python source through MCP/CST tools, not by raw line rewrite.

Target file:

```text
code_analysis/commands/write_project_text_lines_command.py
```

## What was successfully changed

A helper block was added through CST tooling:

```python
PLAIN_TEXT_WRITE_SUFFIXES = frozenset(
    {
        ".adoc",
        ".md",
        ".rst",
        ".txt",
    }
)


def _reject_if_not_plain_text_path(file_path: str) -> ErrorResult | None:
    """Return an error when a path is not an allowed plain-text file."""
    suffix = Path(file_path).suffix.lower()
    if suffix in PLAIN_TEXT_WRITE_SUFFIXES:
        return None
    return ErrorResult(
        message=(
            "write_project_text_lines supports only plain text files "
            f"with suffixes: {', '.join(sorted(PLAIN_TEXT_WRITE_SUFFIXES))}. "
            "Use JSON/YAML/Python-specific commands for structured or code files."
        ),
        code="TEXT_FILE_SUFFIX_NOT_ALLOWED",
        details={
            "file_path": file_path,
            "suffix": suffix,
            "allowed_suffixes": sorted(PLAIN_TEXT_WRITE_SUFFIXES),
        },
    )
```

A small early check was also applied in `execute`:

```python
plain_text_error = _reject_if_not_plain_text_path(file_path)
if plain_text_error is not None:
    return plain_text_error
```

The larger replacement that removes `update_file_data_atomic_batch(...)` was not completed.

## Problem 1 — `cst_modify_tree` could not insert a statement after an inner `If`

Attempted operation:

```text
cst_modify_tree
operation: insert
target_node_id: If node for `if blocked is not None`
position: after
parent: IndentedBlock
```

Observed error:

```text
INVALID_OPERATION
Nodes were not inserted relative to target node ... in parent ...
Target node type: If, Parent node type: IndentedBlock.
```

Why this blocked work:

The desired patch needed to insert a sibling statement immediately after:

```python
if blocked is not None:
    return blocked
```

but before range validation. This is a normal Python statement insertion inside a function body. The CST tool failed to perform it even though the target node is a direct statement in an `IndentedBlock`.

Expected behavior:

`cst_modify_tree` should support inserting a statement before/after a direct statement inside an `IndentedBlock`, or provide a documented `insert_statement_after` operation for this common case.

## Problem 2 — `cst_modify_tree` could not replace an inner `If` statement

Attempted operation:

```text
cst_modify_tree
operation: replace
node_id: If node for `if blocked is not None`
replacement: original if + new plain_text_error check
```

Observed error:

```text
INVALID_OPERATION
Node ... was not replaced.
Node type: If, Parent type: IndentedBlock, start_line=262, end_line=263.
Hint: Replace only works for direct body statements (e.g. in Module or IndentedBlock).
For inner nodes use replace_range or replace the parent.
```

Why this is contradictory:

The node was an `If` statement directly inside a function-body `IndentedBlock`. The error says replacement works for direct body statements in an `IndentedBlock`, but then rejects this exact situation.

Expected behavior:

Replacing a direct statement inside a function `IndentedBlock` should work. If not supported, the error message should not say direct `IndentedBlock` statements are supported.

## Problem 3 — `cst_modify_tree` preview for module-level insert/replace produced unsafe diffs

Attempted operation:

```text
cst_modify_tree
preview=true
operations:
- delete unused imports
- insert helper after logger assignment
- replace execute method
```

Observed behavior:

The preview appeared to damage surrounding module/class structure. In particular, preview output suggested that the `WriteProjectTextLinesCommand(BaseMCPCommand)` class header could lose or distort the base class information.

Why this blocked work:

Because the preview was not trustworthy, the operation was not applied. Applying a CST patch that appears to alter the class declaration would be unsafe.

Expected behavior:

CST preview must preserve unrelated syntax exactly. If the requested operation is invalid, the tool should fail explicitly instead of returning a preview that appears to corrupt unrelated code.

## Problem 4 — `query_cst` range replacement sometimes reported `replaced=1` with an empty diff

Observed command pattern:

```text
query_cst
start_line: 403
end_line: 422
code_lines: replacement block
preview: true
```

Observed result:

```text
success=true
preview=true
replaced=1
diff=""
modified_source contains the intended change
```

Why this blocked work:

A preview that says `replaced=1` but returns an empty diff is ambiguous. The `modified_source` showed the expected edit, but the empty diff made it impossible to rely on the preview as an audit artifact.

Expected behavior:

If `modified_source` differs from the file, `diff` should show the change. If there is no actual change, `replaced` should be `0` or the tool should explain why no diff is produced.

## Problem 5 — `query_cst` preview/apply semantics were difficult to trust without immediate read-back

Observed behavior:

Some `query_cst` calls returned successful results with `modified_source`, but a subsequent `read_project_text_file` showed that the file had not changed when preview was expected, or that only part of the intended change was actually present after later operations.

This may be correct for `preview=true`, but combined with empty diffs and `replaced=1`, it made the state difficult to reason about.

Expected behavior:

The response should clearly distinguish:

```text
preview_only: true/false
file_written: true/false
backup_uuid: present only when written
changed_ranges: explicit
```

## Problem 6 — `compose_cst_module` preview succeeded, but apply failed due to unrelated validation gate

Attempted operation:

```text
compose_cst_module
selector: block_id for method:WriteProjectTextLinesCommand.execute
apply=false -> preview looked correct
apply=true -> failed
```

Observed failure on apply:

```text
Docstring validation failed
Found 25 mypy errors
```

Why this blocked work:

The intended patch was local to one method and compiled successfully in preview, but save/apply was blocked by whole-file validation checks that appear to include pre-existing docstring/mypy issues unrelated to the edit.

Expected behavior:

For a local CST edit, the tool should support at least one of these modes:

```text
validate_syntax_only=true
validate_changed_blocks_only=true
ignore_existing_validation_errors=true
```

A hotfix should not be blocked by unrelated pre-existing mypy/docstring errors unless the patch introduces new errors.

## Problem 7 — large CST payloads were blocked by the outer safety filter

Observed behavior:

When replacing the entire `execute` method through CST tools, the tool call was blocked before reaching the MCP server:

```text
This tool call was blocked by OpenAI safety systems.
```

Why this blocked work:

The full method replacement was the cleanest and safest semantic patch, but the payload size/content triggered an external filter. This forced the work into smaller fragile operations.

Expected behavior:

The CST editing workflow should support large method replacement through a server-side mechanism that avoids sending the entire method body in one tool call, for example:

```text
upload/prepare replacement buffer
preview by buffer_id
apply by buffer_id
```

or a dedicated `replace_block_from_file` / `replace_block_from_artifact` workflow.

## Problem 8 — missing straightforward operation: replace a line range as CST with validation

The needed operation was simple:

```text
Replace lines 403-422 with this valid Python statement block, preserving indentation and validating syntax.
```

But the available paths were awkward:

- `cst_modify_tree` had node insertion/replacement issues.
- `compose_cst_module` was blocked by unrelated validation.
- `query_cst` reported empty diffs for non-empty changes.
- large payloads were blocked externally.

Expected tool:

```text
cst_replace_range(
  file_path,
  start_line,
  end_line,
  code_lines,
  validate_syntax=true,
  preview=true|false,
  create_backup=true
)
```

with reliable diff and explicit write status.

## Problem 9 — command result fields are not strong enough for safe editing workflows

Several CST responses were hard to use because they did not always provide all of these fields consistently:

```text
preview_only
file_written
backup_uuid
changed_ranges
syntax_valid
diff
old_node_id/new_node_id
validation_scope
```

Expected behavior:

Every edit-capable CST command should return a durable, audit-friendly result. A model must not infer whether a file changed from indirect clues.

## Impact on the hotfix

Because of the CST/tooling issues above, the hotfix was only partially applied.

Still needed in `write_project_text_lines_command.py`:

1. Remove unused imports:

```python
from ..core.database_client.file_data_batch import update_file_data_atomic_batch
from ..core.database_client.objects.base import BaseObject
```

2. Replace this block:

```python
file_mtime = BaseObject._to_timestamp(last_modified) or 0.0
# Single logical-write RPC (transaction_id=None); avoid a long-lived outer
# transaction with multiple execute_batch calls — reduces DB lock / driver churn.
update_result = update_file_data_atomic_batch(
    database=database,
    file_id=file_id,
    project_id=project_id,
    source_code=source_code,
    file_path=str(absolute_path),
    file_mtime=file_mtime,
)

if not update_result.get("success"):
    _restore_file_from_backup()
    return ErrorResult(
        message="Failed to update file data: "
        + update_result.get("error", "unknown"),
        code="UPDATE_FILE_DATA_ERROR",
        details=update_result,
    )
```

with:

```python
update_result = {
    "success": True,
    "file_id": file_id,
    "file_path": str(absolute_path),
    "metadata_updated": True,
    "structural_index_skipped": True,
    "reason": "plain_text_file",
}
```

3. Update command schema/help text so it no longer says text writes update DB through `update_file_data_atomic_batch`.

4. Add tests proving `.md` does not call Python AST/index update.

## Recommended CST/tool fixes

1. Make `cst_modify_tree` support insert before/after direct statements inside `IndentedBlock`.
2. Make `cst_modify_tree` support replacing direct statements inside `IndentedBlock` or correct the error message.
3. Make `query_cst` always return a non-empty diff when `modified_source` differs.
4. Add explicit `file_written` and `preview_only` result fields.
5. Add `cst_replace_range` for syntax-validated range replacement.
6. Add an apply mode that ignores unrelated pre-existing docstring/mypy errors while still validating syntax.
7. Add buffer-based method/block replacement to avoid large payload blocking.
8. Return stable changed ranges and backup UUIDs for every write.

## Status

This file documents CST/tooling problems only. It does not complete the source hotfix.
