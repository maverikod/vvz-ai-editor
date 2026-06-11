# 01. Write config and eligibility tests

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Add focused tests for config validation, config generation, and Markdown eligibility.

## Inputs

- [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)
- [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)

## Actions

1. Add tests for missing `docs_indexing` being valid.
2. Add tests for disabled defaults.
3. Add tests for invalid roots.
4. Add tests for documented include-pattern behavior: strict validator rejection or allowed broad patterns with runtime `.md` suffix check.
5. Add tests for valid `docs/**/*.md` and `README.md` patterns.
6. Add tests for eligibility accepted, rejected, and excluded paths.

## Output

Code changes plus:

```text
unit-test-results.md
```

## Verification

Run the smallest relevant test subset and record command, result, and failures.