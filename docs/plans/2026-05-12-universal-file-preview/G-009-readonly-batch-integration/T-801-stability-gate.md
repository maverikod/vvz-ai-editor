# T-801 Stability Gate — universal_file_preview

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Purpose

This document records the stability confirmation required before
`universal_file_preview` is added to `READ_ONLY_BATCH_WHITELIST`.

The whitelist edit (T-802) must NOT proceed until all criteria below
are confirmed TRUE by a reviewer.

## Stability Criteria (all must be TRUE)

- [ ] **C-001 implemented**: `UniversalFilePreviewCommand` is fully implemented
  and registered in `hooks_register_part2.py`.
- [ ] **All handlers implemented**: PythonFileHandler, TextFileHandler,
  JsonFileHandler, JsonLinesFileHandler, YamlFileHandler all pass their tests.
- [ ] **Public schema frozen**: `get_schema()` is frozen; no breaking changes
  anticipated.
- [ ] **Test suite green**: all tests in `tests/test_universal_file_preview*.py`
  pass.

## Sign-off

Reviewer: _________________  Date: _________________

Confirmation (write TRUE when confirmed): _________________

If any criterion is NOT TRUE, do not proceed to T-802.
