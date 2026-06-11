# 02. Write rollout notes and final report

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Write rollout notes, compatibility notes, and final implementation report.

## Inputs

- [../09-tests-and-mcp-verification/mcp-verification-results.md](../09-tests-and-mcp-verification/mcp-verification-results.md)
- [../09-tests-and-mcp-verification/known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md)
- [01-update-user-docs.md](01-update-user-docs.md)

## Actions

1. Summarize implemented config behavior.
2. Summarize validator and generator behavior.
3. Summarize watcher, chunking, and vectorization behavior.
4. List compatibility guarantees.
5. List known limitations.
6. List MCP verification commands and results.
7. State whether server restart is required.

## Output

Create or update:

```text
rollout-notes.md
compatibility-notes.md
final-implementation-report.md
```

## Verification

Final report must include command evidence, result status, and links to test result files.
