#!/usr/bin/env python
"""
S3 verification: normalize_ggrep_match produces Finding objects.
Run: cd /home/vasilyvz/projects/tools/ai_editor && .venv/bin/python scripts/verify_s3_ggrep.py
"""
from __future__ import annotations

import sys

from ai_editor.commands.search_paginated_ggrep import normalize_ggrep_match
from ai_editor.core.search_session.finding import Finding, FindingSource

passed = 0
failed = 0


def check(label: str, cond: bool) -> None:
    global passed, failed
    if cond:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


print("=== S3 normalize_ggrep_match ===")

# 1. Enriched match with node_ref in evidence
raw1 = {
    "file_path": "ai_editor/commands/foo.py",
    "relative_path": "ai_editor/commands/foo.py",
    "score": 0.65,
    "node_ref": "node-abc-123",
    "evidence": {"node_ref": "node-abc-123", "enrichment_status": "enriched"},
    "enrichment_status": "enriched",
    "line_number": 42,
}
f1 = normalize_ggrep_match(raw1, index=0)
check("returns Finding", isinstance(f1, Finding))
check("stable_id from raw.node_ref", f1 and f1.stable_id == "node-abc-123")
check("source is grep", f1 and f1.source == FindingSource.grep)
check("file_path preserved", f1 and f1.file_path == "ai_editor/commands/foo.py")
check("result_id grep-000000", f1 and f1.result_id == "grep-000000")
check("score via score_for_source", f1 and 0.0 <= f1.score <= 1.0)

# 2. node_ref only in evidence (not on raw)
raw2 = {
    "file_path": "ai_editor/core/x.py",
    "score": 0.4,
    "evidence": {"node_ref": "ev-node-456"},
}
f2 = normalize_ggrep_match(raw2, index=1)
check("stable_id from evidence.node_ref", f2 and f2.stable_id == "ev-node-456")

# 3. block_id fallback (no node_ref anywhere)
raw3 = {
    "file_path": "ai_editor/core/y.py",
    "score": 0.2,
    "block_id": "blk-789",
    "evidence": {},
}
f3 = normalize_ggrep_match(raw3, index=2)
check("stable_id from raw.block_id", f3 and f3.stable_id == "blk-789")

# 4. block_id in evidence fallback
raw4 = {
    "file_path": "ai_editor/core/z.py",
    "score": 0.1,
    "evidence": {"block_id": "ev-blk-999"},
}
f4 = normalize_ggrep_match(raw4, index=3)
check("stable_id from evidence.block_id", f4 and f4.stable_id == "ev-blk-999")

# 5. no stable_id at all -> None
raw5 = {
    "file_path": "ai_editor/core/empty.py",
    "score": 0.9,
    "evidence": {},
}
f5 = normalize_ggrep_match(raw5, index=4)
check("no stable_id -> None", f5 is None)

# 6. no file_path -> None
raw6 = {
    "score": 0.9,
    "node_ref": "some-ref",
    "evidence": {},
}
f6 = normalize_ggrep_match(raw6, index=5)
check("no file_path -> None", f6 is None)

# 7. relative_path fallback for file_path
raw7 = {
    "relative_path": "ai_editor/core/rel.py",
    "score": 0.5,
    "node_ref": "rel-node-111",
    "evidence": {},
}
f7 = normalize_ggrep_match(raw7, index=6)
check("file_path from relative_path", f7 and f7.file_path == "ai_editor/core/rel.py")

# 8. to_dict / from_dict round-trip
if f1:
    d = f1.to_dict()
    check("to_dict has stable_id", "stable_id" in d)
    f_back = Finding.from_dict(d)
    check("from_dict round-trip", f_back == f1)

print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
