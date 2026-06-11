#!/usr/bin/env python
"""
S2 verification: normalize_cross_finding produces Finding objects.
Run: cd /workspace && .venv/bin/python scripts/verify_s2_normalize.py
"""
from __future__ import annotations

import sys

from ai_editor.commands.search_paginated_cross import normalize_cross_finding
from ai_editor.core.search_session.finding import Finding, FindingSource

passed = 0
failed = 0

def check(label, cond):
    global passed, failed
    if cond:
        print(f'  PASS  {label}')
        passed += 1
    else:
        print(f'  FAIL  {label}')
        failed += 1

print('=== S2 normalize_cross_finding ===')

# 1. Structural cross row with node_ref in evidence
raw1 = {
    'file_path': 'ai_editor/commands/foo.py',
    'score': 0.82,
    'evidence': {'node_ref': 'abc-123', 'source_mode': 'structural'},
    'source_mode': 'structural',
}
f1 = normalize_cross_finding(raw1, index=0)
check('returns Finding', isinstance(f1, Finding))
check('stable_id from evidence.node_ref', f1 and f1.stable_id == 'abc-123')
check('score clamped 0.82', f1 and abs(f1.score - 0.82) < 1e-9)
check('source is cross', f1 and f1.source == FindingSource.cross)
check('file_path preserved', f1 and f1.file_path == 'ai_editor/commands/foo.py')
check('result_id cross-000000', f1 and f1.result_id == 'cross-000000')

# 2. node_ref on raw directly (not in evidence)
raw2 = {
    'file_path': 'ai_editor/core/x.py',
    'score': 0.5,
    'node_ref': 'raw-node-456',
    'evidence': {'source_mode': 'structural'},
}
f2 = normalize_cross_finding(raw2, index=1)
check('stable_id from raw.node_ref', f2 and f2.stable_id == 'raw-node-456')

# 3. block_id fallback
raw3 = {
    'file_path': 'ai_editor/core/y.py',
    'score': 0.3,
    'evidence': {'block_id': 'blk-789', 'source_mode': 'structural'},
}
f3 = normalize_cross_finding(raw3, index=2)
check('stable_id from evidence.block_id', f3 and f3.stable_id == 'blk-789')

# 4. classic_line with require_structural=True -> None
raw4 = {
    'file_path': 'ai_editor/core/z.py',
    'score': 0.1,
    'evidence': {'node_ref': 'some-ref', 'source_mode': 'classic_line'},
}
f4 = normalize_cross_finding(raw4, index=3, require_structural_grep=True)
check('classic_line + require_structural -> None', f4 is None)

# 5. classic_line with require_structural=False -> Finding
f5 = normalize_cross_finding(raw4, index=3, require_structural_grep=False)
check('classic_line + require_structural=False -> Finding', isinstance(f5, Finding))

# 6. no stable_id at all -> None
raw6 = {
    'file_path': 'ai_editor/core/empty.py',
    'score': 0.9,
    'evidence': {},
}
f6 = normalize_cross_finding(raw6, index=4)
check('no stable_id -> None', f6 is None)

# 7. to_dict round-trip
if f1:
    d = f1.to_dict()
    check('to_dict has stable_id', 'stable_id' in d)
    check('to_dict has score', 'score' in d)
    f_back = Finding.from_dict(d)
    check('from_dict round-trip', f_back == f1)

print(f'\n=== {passed} passed, {failed} failed ===')
sys.exit(0 if failed == 0 else 1)
