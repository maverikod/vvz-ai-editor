# Atomic step: indexing worker current behavior

Parent step: 01-current-state-inventory

Source file or area:
code_analysis/core/indexing_worker_pkg/**
code_analysis/core/indexing_worker_pkg/vectorize_after_index.py

Goal:
Document how files become chunks today, how indexing work is scheduled, how chunk rows are written, and how vectorize-after-index is triggered.

Output:
docs/plans/2026-05-04-docs-markdown-indexing-vectorization/01-current-state-inventory/indexing-observations.md

Rules:
Observation only. Do not change source code in this atomic step.
