# Atomic step: field values

Parent step: 03-config-validator-generator

Source file:
code_analysis/core/config_validator/field_values.py

Goal:
Add or reuse value checks for safe project-relative paths, no absolute roots, no path traversal, and Markdown-only include patterns.

Output:
Validator value implementation and notes in this step directory.

Rules:
Document chosen matcher behavior. Runtime `.md` suffix enforcement remains mandatory.
