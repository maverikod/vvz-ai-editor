# 01. Update user documentation

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Update user-facing documentation after implementation.

## Inputs

- [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)
- [../09-tests-and-mcp-verification/mcp-verification-results.md](../09-tests-and-mcp-verification/mcp-verification-results.md)
- [../09-tests-and-mcp-verification/known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md)

## Inspect and update

- `docs/COMMANDS_GUIDE.md`
- `docs/PROJECT_RULES.md`
- `docs/METADATA_SCHEMA_STANDARD.md` if command metadata/schema docs changed

## Actions

1. State that docs indexing is Markdown-only.
2. State that docs indexing is disabled by default.
3. State that docs vectorization is disabled by default.
4. Show the `code_analysis.docs_indexing` config section.
5. State that `projectid` is not used for this setting.
6. State when semantic search can return Markdown docs.

## Output

Create or update:

```text
documentation-change-notes.md
```

## Verification

Read the updated docs and confirm all required statements are present.