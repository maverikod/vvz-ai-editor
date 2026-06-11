# Step 01: code_analysis/core/file_handlers/registry.py

## Scope

Create the extension-to-handler registry. This step must not implement handlers or universal commands.

Owned files:

- `code_analysis/core/file_handlers/__init__.py`
- `code_analysis/core/file_handlers/registry.py`
- tests for registry lookup only

Do not edit `.venv`, `site-packages`, installed packages, or command files in this step.

## Current-code reads before edits

Run these MCP checks first:

```text
list_project_files file_pattern=code_analysis/core/file_handlers/* python_only=false
read_project_text_file code_analysis/commands/project_text_file_guard.py lines 1-220
read_project_text_file code_analysis/commands/write_project_text_lines_command.py lines 1-120
read_project_text_file code_analysis/commands/read_project_text_file_command.py lines 1-260
fulltext_search FORBIDDEN_PYTHON_SOURCE_SUFFIXES
fulltext_search PLAIN_TEXT_WRITE_SUFFIXES
```

Record in `observations.md` whether `code_analysis/core/file_handlers/` already exists. Current audit found that it does not exist.

## Implementation

1. Add a small registry module with explicit handler ids:

```text
text
json
yaml
python
```

2. Add default extension mapping:

```text
.md, .txt, .rst, .adoc -> text
.json                   -> json
.yaml, .yml             -> yaml
.py, .pyi, .pyw         -> python
```

3. Do not map `.toml`. It must return unsupported until a TOML policy is explicitly designed.

4. Unknown suffixes must fail closed.

5. Add operation-aware validation. Required operations:

```text
read
save
replace
delete
```

6. Provide these APIs:

```text
resolve_handler(file_path, operation)
validate_supported(file_path, operation)
get_handler_schema(handler_id, operation)
list_handler_mappings()
```

7. Error for unsupported extension must include:

```text
code=UNSUPPORTED_FILE_EXTENSION
details.file_path
details.suffix
details.operation
```

8. Error for unsupported operation must include:

```text
code=UNSUPPORTED_FILE_OPERATION
details.file_path
details.handler_id
details.operation
```

## Validation

Unit or MCP-invoked test expectations:

```text
README.md + read     -> text
notes.txt + replace  -> text
docs/a.rst + save    -> text
docs/a.adoc + delete -> text
config.json + read   -> json
config.yaml + read   -> yaml
config.yml + read    -> yaml
src/app.py + read    -> python
src/app.pyi + read   -> python
src/app.pyw + read   -> python
pyproject.toml       -> UNSUPPORTED_FILE_EXTENSION
file.unknown         -> UNSUPPORTED_FILE_EXTENSION
```

## Read-back verification

After writing source files, use `read_project_text_file` to verify the created files. Do not rely only on test output.

## Observations entry

Append:

```text
Step: 01 registry
Current code reads:
Implementation summary:
Validation commands:
Read-back verification:
Status:
```

## Stop condition

Stop and report if existing config infrastructure makes the registry location unclear. Do not invent a global config format without reading current configuration code first.
