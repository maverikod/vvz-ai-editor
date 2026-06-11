# 01. Implement Markdown eligibility helper

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Create one reusable helper that decides whether a project file is eligible for docs indexing.

## Inputs

- [../02-config-contract/index.md](../02-config-contract/index.md)
- [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)

## Actions

1. Choose the module for the helper after inspecting watcher code.
2. Normalize paths to project-relative POSIX form.
3. Return false when docs indexing is disabled.
4. Return false when suffix is not `.md`.
5. Apply roots, include patterns, and exclude patterns.
6. Make exclude rules override include rules.
7. Return a reason code for diagnostics.

## Output

Code change plus notes in:

```text
eligibility-rules.md
```

## Verification

Add small tests for accepted, excluded, and non-md paths.
