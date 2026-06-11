# Step 02: code_analysis/core/file_handlers/base.py

- Define the handler contract for read/save/replace/delete.
- Add common request/result dataclasses for file handler operations.
- Require validate_before_side_effects(request) for every mutating operation.
- Require every handler to expose operation-specific JSON schemas.
- Standardize errors: unsupported_operation, unsupported_extension, validation_failed, side_effect_blocked.
- Acceptance: each concrete handler can be checked for all four operations before command registration.
