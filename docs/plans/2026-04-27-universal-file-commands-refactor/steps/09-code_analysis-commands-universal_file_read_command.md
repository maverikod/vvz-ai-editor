# Step 09: code_analysis/commands/universal_file_read_command.py

## Scope

Add `universal_file_read` as an explicit MCP command. Do not name the public command `read`.

Owned files:

- `code_analysis/commands/universal_file_read_command.py`
- command registration files only if needed for this command
- focused tests for read routing

Do not implement write/save/replace/delete in this step.

## Current-code reads before edits

Run these MCP reads/searches first:

```text
read_project_text_file code_analysis/commands/read_project_text_file_command.py lines 1-380
read_project_text_file code_analysis/commands/get_file_lines_command.py lines 1-360
fulltext_search json_load_file
fulltext_search load_file_to_tree
fulltext_search cst_load_file query_cst get_file_lines
read_project_text_file code_analysis/core/file_handlers/registry.py lines 1-260
```

Record current compatibility behavior in `observations.md`:

- Python read currently delegates to `get_file_lines` through `read_project_text_file`.
- Small `.json` read may return structured tree through current JSON loader.

## Implementation

1. Command name must be:

```text
universal_file_read
```

2. Parameters:

```text
project_id
file_path
start_line optional for text/python line view
end_line optional for text/python line view
```

3. Resolve handler with registry before file access.

4. Include selected handler in every success response:

```text
handler_id
operation=read
file_path
project_id
```

5. Routing rules:

```text
.md/.txt/.rst/.adoc -> text read lines
.json               -> JSON handler/tree read
.yaml/.yml          -> YAML handler if implemented, otherwise documented unsupported-handler error before side effects
.py/.pyi/.pyw       -> Python safe read, preferably existing get_file_lines for line views
.toml/unknown       -> unsupported-extension error before file access side effects
```

6. Do not break `read_project_text_file` compatibility in this step.

7. For JSON, do not implement raw text fallback for write semantics. This is read-only, but response must still identify `handler_id=json`.

## Validation

Required MCP checks after registration:

```text
universal_file_read on README.md -> handler_id=text
universal_file_read on .txt -> handler_id=text
universal_file_read on .json -> handler_id=json
universal_file_read on .py -> handler_id=python or documented safe Python read response
universal_file_read on .toml -> UNSUPPORTED_FILE_EXTENSION
universal_file_read on unknown suffix -> UNSUPPORTED_FILE_EXTENSION
```

For each successful read, verify the response contains:

```text
success=true
handler_id
operation=read
file_path
project_id
```

## Read-back verification

After writing command/registration files, read them back with `read_project_text_file`.

## Observations entry

Append:

```text
Step: 09 universal_file_read
Current code reads:
Implementation summary:
MCP validation:
Compatibility notes:
Status:
```

## Stop condition

Stop and report if registry from Step 01 is not available or command registration location is unclear after reading current command registration code.
