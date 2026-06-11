# Step 04: code_analysis/core/file_handlers/text_ranges.py

- Add a dedicated parser for text range syntax.
- Support [12], [12,15], [:12], [11:] and an internal canonical representation.
- Document and enforce 1-based line numbering.
- Document and enforce inclusive end lines for command compatibility.
- Reject negative indexes unless explicitly added later.
- Validate out-of-range behavior before write: clamp for read, strict validation for replace/save/delete.
- Reject overlapping multi-ranges unless a later spec explicitly permits them.
- Acceptance: parser unit tests cover single-line, closed range, open start, open end, empty, invalid, reversed, and overlapping ranges.
