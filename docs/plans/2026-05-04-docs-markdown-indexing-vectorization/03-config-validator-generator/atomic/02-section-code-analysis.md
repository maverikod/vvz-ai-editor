# Atomic step: section code analysis

Parent step: 03-config-validator-generator

Source file:
code_analysis/core/config_validator/section_code_analysis.py

Goal:
Add or extend validation rules for `code_analysis.docs_indexing` fields: enabled, vectorize, roots, include, and exclude.

Output:
Validator implementation and notes in this step directory.

Rules:
Invalid fields must produce structured ValidationResult errors with section and key context.
