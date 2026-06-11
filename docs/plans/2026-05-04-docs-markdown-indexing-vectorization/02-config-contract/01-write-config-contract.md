# 01. Write docs_indexing config contract

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Write a precise contract for `code_analysis.docs_indexing`.

## Inputs

- [index.md](index.md)
- [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)

## Actions

1. Describe `enabled`, `vectorize`, `roots`, `include`, and `exclude`.
2. State defaults clearly.
3. State that settings are in main config, not `projectid`.
4. State that only `.md` files are supported.
5. State that old configs without the section remain valid.

## Output

Create or update:

```text
config-contract.md
```

## Verification

The output must contain a complete JSON example and default values.
