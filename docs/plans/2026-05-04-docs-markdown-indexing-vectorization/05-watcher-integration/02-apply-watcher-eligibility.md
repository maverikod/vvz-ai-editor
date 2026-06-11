# 02. Apply watcher eligibility

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Use the Markdown eligibility helper inside the watcher path.

## Inputs

- [01-locate-watcher-config-entry.md](01-locate-watcher-config-entry.md)
- [../04-markdown-eligibility/01-implement-eligibility-helper.md](../04-markdown-eligibility/01-implement-eligibility-helper.md)

## Actions

1. Load docs indexing settings from config.
2. Call the eligibility helper for candidate documentation files.
3. Keep current behavior unchanged when `enabled=false`.
4. Pass only eligible `.md` files to the existing indexing path.
5. Record skip reasons for diagnostics.
6. Add focused tests for watcher behavior.

## Output

Code changes plus notes in:

```text
watcher-skip-reasons.md
watcher-test-cases.md
```

## Verification

Test enabled and disabled configs on a dedicated test project only.
