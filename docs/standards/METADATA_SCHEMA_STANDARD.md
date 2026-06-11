# Command Metadata and Schema Standard

This document defines the project standard for describing MCP command input schemas and extended command metadata in `code_analysis`.

The external MCP/API surface is owned by `mcp-proxy-adapter`. The `code_analysis` project is responsible for registering command classes and providing command descriptions in a consistent format that the adapter can expose through `help`, OpenAPI, and MCP tooling.

Canonical copy (standards tree): [`standards/METADATA_SCHEMA_STANDARD.md`](standards/METADATA_SCHEMA_STANDARD.md).

## Adapter integration (`mcp-proxy-adapter` >= 8.10.13)

Requires **`mcp-proxy-adapter>=8.10.13`** (see `pyproject.toml` / `requirements.txt`).

The adapter builds help via `build_command_help_payload()`:

- **`schema`** — from the command’s `get_schema()` only (input parameters, `additionalProperties`, enums, defaults).
- **`metadata` / `ai_metadata`** — from the command’s `metadata()`; keys such as `detailed_description`, `parameters`, `return_value`, `usage_examples`, `error_cases`, and `best_practices` are merged for `help` / MCP tooling.

Do **not** put validation-only input fields only in `metadata()`; they must appear in `get_schema()`. Do **not** embed transport envelopes (`server_id`, `copy_number`, …) in command `metadata()` usage examples.

## Scope

This standard applies to command implementations under `code_analysis/commands`.

It covers two separate description layers:

1. `get_schema()` — the machine-readable input schema used for request validation and adapter-facing command help.
2. `metadata()` — the extended AI/documentation metadata used to explain behavior, examples, return values, error cases, and safe usage.

Do not merge these two responsibilities into one structure.

## Required command class shape

Every new MCP command class should define these class attributes and methods:

```python
class SomeCommand(BaseMCPCommand):
    name = "some_command"
    version = "1.0.0"
    descr = "Short command description"
    category = "custom"
    author = "..."
    email = "..."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_some_command_schema()

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        # Optional semantic validation goes here.
        return params

    def execute(self, ...) -> Dict[str, Any]:
        ...

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_some_command_metadata(cls)
```

For small commands, `get_schema()` may return the schema inline. For non-trivial commands, place schema and metadata in separate modules.

Preferred layout for complex commands:

```text
code_analysis/commands/some_command.py
code_analysis/commands/some_command_schema.py
code_analysis/commands/some_command_metadata.py
```

For very large documentation blocks, metadata may be split further:

```text
some_command_metadata.py
some_command_metadata_descr_params.py
some_command_metadata_errors_return.py
some_command_metadata_examples.py
```

## `get_schema()` standard

`get_schema()` must return a JSON-Schema-like object with the following top-level shape:

```python
def get_some_command_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project UUID.",
            },
            "dry_run": {
                "type": "boolean",
                "default": True,
                "description": "Preview changes without applying them.",
            },
        },
        "required": ["project_id"],
        "additionalProperties": False,
    }
```

### Supported schema subset

`BaseMCPCommand.validate_params_against_schema()` currently enforces this practical subset:

- `type`
- `properties`
- `required`
- `additionalProperties`
- `enum`

The validator explicitly supports these property types:

- `string`
- `integer`
- `number`
- `boolean`
- `array`
- `object`

The following fields may be used for documentation and adapter-facing help, but do not rely on the base validator to enforce all nested semantics:

- `default`
- `description`
- `items`
- nested `properties`
- nested `required`
- `oneOf`

If a command needs deeper validation, implement it in `validate_params()` after calling `super().validate_params(params)`.

### Schema rules

1. Always set `additionalProperties` explicitly.
2. Prefer `additionalProperties: False` unless the command intentionally accepts arbitrary keys.
3. Every public parameter accepted by `execute()` must be present in `properties`.
4. Every required runtime parameter must be listed in `required`.
5. Use `enum` for fixed modes, actions, status values, and output formats.
6. Use `default` only when the implementation actually handles an omitted value as that default.
7. Use clear `description` text for every property.
8. Use `items` for arrays.
9. Use nested `properties` and nested `required` for object elements in arrays.
10. Add command-specific semantic validation in `validate_params()` for IDs, path safety, existence checks, mutually exclusive parameters, and destructive-operation guards.

### Project and path parameters

Project-scoped commands should use:

```python
"project_id": {
    "type": "string",
    "description": "Project UUID. Use list_projects to discover valid project_id values.",
}
```

Path parameters should state whether the path is project-relative, absolute, literal, or glob-like.

Examples:

```python
"file_path": {
    "type": "string",
    "description": "Literal project-relative file path. Wildcards are not allowed.",
}
```

```python
"file_pattern": {
    "type": "string",
    "description": "Optional project-relative fnmatch pattern. `*` may cross `/`.",
}
```

### Destructive and write commands

Commands that modify files, database rows, queue state, or project lifecycle state must expose at least one safe preview/control field when technically possible:

- `dry_run`
- `preview`
- `backup`
- `confirm`
- `delete_from_disk`
- `hard_delete`

The schema description must make the safety behavior explicit.

Example:

```python
"dry_run": {
    "type": "boolean",
    "default": True,
    "description": "Preview affected records without modifying files or database rows.",
}
```

### Mutually exclusive or conditional parameters

JSON Schema may describe complex combinations with `oneOf`, but the base validator does not fully enforce deep `oneOf` semantics. Enforce these rules in `validate_params()`.

Examples that require semantic validation:

- exactly one of `node_id` or `selector`
- `project_id` and `file_path` must be provided together
- `delete_from_disk=True` requires explicit test-project validation
- `start_line <= end_line`
- file suffix must be supported by the selected handler

## `metadata()` standard

`metadata()` must return a documentation-oriented dictionary. It is intended for AI models, generated docs, and rich help. It should be more explanatory than `get_schema()`.

Recommended structure:

```python
def get_some_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": "...",
        "parameters": {
            "project_id": {
                "description": "...",
                "type": "string",
                "required": True,
                "examples": ["..."],
            },
        },
        "return_value": {
            "success": {
                "description": "...",
                "data": {...},
                "example": {...},
            },
            "error": {
                "description": "...",
                "code": "...",
                "message": "...",
                "details": "...",
            },
        },
        "usage_examples": [
            {
                "description": "...",
                "command": {...},
                "explanation": "...",
            },
        ],
        "error_cases": {
            "ERROR_CODE": {
                "description": "...",
                "message": "...",
                "solution": "...",
            },
        },
        "best_practices": [
            "...",
        ],
    }
```

### Required metadata fields

Every metadata dictionary should include:

- `name`
- `version`
- `description`
- `category`
- `author`
- `email`
- `detailed_description`
- `parameters`
- `return_value`
- `usage_examples`
- `error_cases`
- `best_practices`

### Metadata parameter entries

Each `parameters` entry should include:

- `description`
- `type`
- `required`

Use these when helpful:

- `default`
- `examples`
- `enum`
- `items`
- `notes`

The metadata `parameters` block may be more explanatory than the schema, but it must not contradict `get_schema()`.

## Return value documentation

Metadata must describe both success and error shapes.

Recommended success block:

```python
"return_value": {
    "success": {
        "description": "Command completed successfully.",
        "data": {
            "success": "Always True on success.",
            "items": "List of returned rows.",
            "count": "Number of returned rows.",
        },
        "example": {
            "success": True,
            "items": [],
            "count": 0,
        },
    },
    "error": {
        "description": "Command failed.",
        "code": "Stable error code.",
        "message": "Human-readable error message.",
        "details": "Additional diagnostic fields when available.",
    },
}
```

Error codes documented in `error_cases` should match codes actually returned by the command.

## Usage examples

Every non-trivial command should include at least one usage example. Write examples as parameter dictionaries, not as transport-specific JSON-RPC envelopes.

Good:

```python
{
    "description": "List active projects",
    "command": {"include_deleted": False},
    "explanation": "Returns only non-deleted projects.",
}
```

Avoid:

```python
{
    "command": {
        "server_id": "code-analysis-server",
        "copy_number": 1,
        "command": "list_projects",
        "params": {"include_deleted": False},
    }
}
```

Transport-specific examples belong in adapter or proxy documentation, not command metadata.

## Error case documentation

Each error case should include:

- stable error code
- when it happens
- expected message pattern
- recovery or solution

Example:

```python
"PROJECT_NOT_FOUND": {
    "description": "The project_id does not exist in the database.",
    "message": "Project not found: {project_id}",
    "solution": "Call list_projects and retry with a valid project_id.",
}
```

## Safety documentation

Metadata for write or destructive commands must include safety behavior in both `detailed_description` and `best_practices`.

Required topics when applicable:

- whether the command supports `dry_run` or `preview`
- whether backups are created
- whether changes touch disk, database, queue state, or in-memory state
- whether the operation can be undone
- whether the command is safe for real projects or only for test projects
- how to verify the result with a separate read command

## Validation standard

`get_schema()` handles shallow structural validation. `validate_params()` handles command semantics.

Recommended pattern:

```python
def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
    params = super().validate_params(params)

    project_id = params.get("project_id")
    if project_id:
        self._validate_project_id_exists(project_id)

    if params.get("start_line") and params.get("end_line"):
        if params["start_line"] > params["end_line"]:
            raise ValidationError(
                "start_line must be less than or equal to end_line",
                field="start_line",
                details={"end_line": params["end_line"]},
            )

    return params
```

Validate before queuing long-running work whenever possible so invalid input fails immediately.

## Naming conventions

Use consistent file names:

```text
<command_name>_command.py
<command_name>_schema.py
<command_name>_metadata.py
```

For grouped command modules:

```text
<group>_mcp_commands.py
<group>_mcp_commands_schema.py
<group>_mcp_commands_metadata.py
```

For package-style commands:

```text
code_analysis/commands/<group>/<command>.py
code_analysis/commands/<group>/<command>_schema.py
code_analysis/commands/<group>/<command>_metadata.py
```

## Registration expectations

Command metadata and schemas are only useful when the command class is registered.

Register commands through the appropriate hook module:

```python
reg.register(SomeCommand, "custom")
```

Current registration entry points:

```text
code_analysis/hooks.py
code_analysis/hooks_register_part1.py
code_analysis/hooks_register_part2.py
code_analysis/commands/registration.py
```

Do not implement external API routes in command modules. The adapter owns the external surface.

## Documentation generation expectations

Generated command documentation should be derived from the same source of truth:

- command class attributes
- `get_schema()`
- `metadata()`
- actual `help` output through MCP

Do not maintain a separate hand-written schema that can drift from command code.

## Review checklist for new commands

Before a command is considered complete:

- [ ] Command class has `name`, `version`, `descr`, `category`, `author`, `email`.
- [ ] Command is registered with `reg.register(..., "custom")`.
- [ ] `get_schema()` returns `type=object`.
- [ ] All public parameters are listed under `properties`.
- [ ] `required` matches actual runtime requirements.
- [ ] `additionalProperties` is explicit.
- [ ] Enums are used for fixed modes and actions.
- [ ] Defaults match actual implementation behavior.
- [ ] `validate_params()` performs semantic validation that schema cannot enforce.
- [ ] `metadata()` includes detailed description, parameters, return value, examples, errors, and best practices.
- [ ] Destructive/write behavior is documented and guarded.
- [ ] The command appears in `help` after server restart.
- [ ] The command executes successfully through MCP.
- [ ] The result is verified through a separate read command when the command changes state.

## Good reference implementations

Use these commands as style references:

- `code_analysis/commands/cst_load_file_command.py`
- `code_analysis/commands/cst_load_file_metadata.py`
- `code_analysis/commands/cst_modify_tree_command.py`
- `code_analysis/commands/cst_modify_tree_schema.py`
- `code_analysis/commands/cst_modify_tree_metadata.py`

These examples demonstrate the intended separation between machine schema, command implementation, and extended AI-facing documentation.
