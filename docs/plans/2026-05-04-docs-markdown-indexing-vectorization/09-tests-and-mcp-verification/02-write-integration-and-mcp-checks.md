# 02. Write integration and MCP checks

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Define and run integration checks for watcher, indexing, chunking, vectorization, and search behavior.

## Inputs

- [../05-watcher-integration/index.md](../05-watcher-integration/index.md)
- [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)
- [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)

## Actions

1. Use only a dedicated test project.
2. Verify enabled false behavior.
3. Verify enabled true with vectorize false.
4. Verify enabled true with vectorize true.
5. Verify normal file and chunk records.
6. Verify semantic search returns docs only when vectorized.
7. For queued jobs, inspect nested command success.

## Output

Create or update:

```text
integration-test-results.md
mcp-verification-results.md
known-limitations.md
```

## Verification

Every claim must be backed by an MCP command result and a separate read or search verification.
