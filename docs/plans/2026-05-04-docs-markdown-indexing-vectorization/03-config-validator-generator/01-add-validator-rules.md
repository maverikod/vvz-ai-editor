# 01. Add validator rules

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Add validation rules for `code_analysis.docs_indexing`.

## Inspect first

- `code_analysis/core/config_validator/validator.py`
- `code_analysis/core/config_validator/section_code_analysis.py`
- `code_analysis/core/config_validator/result.py`

## Actions
1. Find how `code_analysis` config fields are validated now.
2. Add optional validation for `docs_indexing`.
3. Validate `enabled` and `vectorize` as booleans.
4. Validate `roots`, `include`, and `exclude` as string arrays.
5. Reject absolute paths and parent traversal.
6. Validate `include` patterns against documented matcher semantics; either reject non-Markdown-resolving patterns or allow broad patterns only when runtime eligibility still enforces `.md` suffix.

## Output

Code changes plus notes in:

```text
validator-change-notes.md
```

## Verification

Add or update tests for valid defaults and invalid non-md patterns.