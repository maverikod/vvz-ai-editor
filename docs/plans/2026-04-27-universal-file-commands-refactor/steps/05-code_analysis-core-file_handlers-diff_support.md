# Step 05: code_analysis/core/file_handlers/diff_support.py

- Add shared unified diff generation for text-like handlers.
- Return changed line ranges in a stable response field.
- Support context line count configuration.
- Use the same diff path for dry_run and apply=true responses.
- Keep this module format-agnostic: it receives before/after text and labels only.
- Acceptance: save/replace with diff=true returns unified diff; dry_run returns the same diff shape and leaves file unchanged.
