# 02. Write Markdown eligibility tests

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Add tests for the docs indexing eligibility helper.

## Inputs

- [01-implement-eligibility-helper.md](01-implement-eligibility-helper.md)
- [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Actions

1. Find the existing test style for config or watcher helpers.
2. Add tests for `docs/guide.md` allowed when enabled.
3. Add tests for `README.md` allowed when included.
4. Add tests for `docs/guide.txt` rejected.
5. Add tests for `docs/plans/task.md` rejected by default exclude.
6. Add tests that exclude wins over include.
7. Add tests for disabled config returning false.

## Output

Code changes plus notes in:

```text
eligibility-test-cases.md
```

## Verification

Run the smallest relevant test subset and record the command/result.
