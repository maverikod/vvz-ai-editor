# 02. Write compatibility notes

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Record compatibility rules for configs and existing indexing behavior.

## Inputs

- [01-write-config-contract.md](01-write-config-contract.md)
- [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Actions

1. State behavior when `docs_indexing` is missing.
2. State behavior when `enabled=false`.
3. State behavior when `enabled=true` and `vectorize=false`.
4. State behavior when `enabled=true` and `vectorize=true`.
5. Record risks and open questions.

## Output

Create or update:

```text
backward-compatibility-notes.md
```

## Verification

The output must mention old configs and existing code indexing behavior.
