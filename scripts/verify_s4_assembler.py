#!/usr/bin/env python
"""
S4 verification: BlockAssembler re-segmentation and relevance ordering.
Run: cd /home/vasilyvz/projects/tools/ai_editor && .venv/bin/python scripts/verify_s4_assembler.py
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from ai_editor.core.search_session.block_assembler import BlockAssembler
from ai_editor.core.search_session.directory import SearchSessionDirectoryLayout
from ai_editor.core.search_session.raw_finding_buffer import RawFindingBuffer
from ai_editor.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    read_index,
)

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


def make_assembler(
    layout: SearchSessionDirectoryLayout, tmp_dir: Path
) -> BlockAssembler:
    entries: list[dict] = []

    def append_index_entry(position: int, completeness: str) -> None:
        block_path = layout.blocks_dir / f"block_{position}.json"
        size = block_path.stat().st_size if block_path.is_file() else 0
        from ai_editor.core.search_session.result_index import append_block_entry
        append_block_entry(
            layout.index_path,
            position=position,
            size_bytes=size,
            completeness=completeness,
        )

    def update_manifest_metrics(metrics: dict) -> None:
        pass  # not needed for this test

    return BlockAssembler(
        layout,
        RawFindingBuffer(layout.buffer_dir),
        max_block_size_bytes=1024 * 1024,  # 1 MB — fits everything in one block
        append_index_entry=append_index_entry,
        update_manifest_metrics=update_manifest_metrics,
    )


print("=== S4 BlockAssembler re-segmentation ===")

tmp = Path(tempfile.mkdtemp(prefix="verify_s4_"))
try:
    # Build a fake session directory layout
    session_dir = tmp / "session"
    session_dir.mkdir()

    # Manually construct layout pointing at session_dir
    layout = SearchSessionDirectoryLayout(root=session_dir, manifest_path=session_dir / 'manifest.json', index_path=session_dir / 'index.json', service_metadata_path=session_dir / 'service_metadata.json', blocks_dir=session_dir / 'blocks', buffer_dir=session_dir / 'buffer', relevance_blocks_dir=session_dir / 'blocks_relevance')  # noqa: E501
    layout.blocks_dir.mkdir(parents=True, exist_ok=True)
    layout.buffer_dir.mkdir(parents=True, exist_ok=True)
    layout.relevance_blocks_dir.mkdir(parents=True, exist_ok=True)

    # Write 5 findings with different scores
    findings = [
        {"result_id": "a", "source": "cross", "file_path": "a.py", "stable_id": "s1", "score": 0.9, "mtime": 100.0},
        {"result_id": "b", "source": "grep",  "file_path": "b.py", "stable_id": "s2", "score": 0.3, "mtime": 200.0},
        {"result_id": "c", "source": "cross", "file_path": "c.py", "stable_id": "s3", "score": 0.7, "mtime": 150.0},
        {"result_id": "d", "source": "grep",  "file_path": "d.py", "stable_id": "s4", "score": 0.5, "mtime": 120.0},
        {"result_id": "e", "source": "cross", "file_path": "e.py", "stable_id": "s5", "score": 0.1, "mtime": 300.0},
    ]
    buffer = RawFindingBuffer(layout.buffer_dir)
    for i, f in enumerate(findings):
        buffer.append_finding(f"f-{i:03d}", f)

    assembler = make_assembler(layout, tmp)

    # Run with search_completed=True -> should finalize immediately
    published = assembler.run_until_idle(search_completed=True)

    # --- temporal blocks ---
    check("published >= 1 temporal block", published >= 1)
    check("block_1.json exists", (layout.blocks_dir / "block_1.json").is_file())

    # --- index completeness ---
    check("index.json exists", layout.index_path.is_file())
    idx = read_index(layout.index_path)
    check("completeness = finished", idx.completeness == COMPLETENESS_FINISHED)

    # --- relevance blocks ---
    rel_dir = layout.relevance_blocks_dir
    rel_blocks = sorted(rel_dir.glob("block_*.json")) if rel_dir.is_dir() else []
    check("at least 1 relevance block written", len(rel_blocks) >= 1)
    check("relevance_blocks in index", len(idx.relevance_blocks) >= 1)

    # Read relevance block_1 and check ordering: score DESC
    if rel_blocks:
        with open(rel_blocks[0]) as fh:
            rel_data = json.load(fh)
        results = rel_data.get("results", [])
        check("relevance block has results", len(results) > 0)
        if len(results) >= 2:
            scores = [r.get("score", 0) for r in results]
            check(
                "relevance sorted score DESC",
                all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
            )
        # First result should be highest score = 0.9 (result_id='a')
        check(
            "first result is highest score",
            results[0].get("result_id") == "a" if results else False,
        )

    # --- idempotent guard ---
    published2 = assembler.run_until_idle(search_completed=True)
    check("idempotent re-run returns 0", published2 == 0)

    # --- buffer deleted after finalize ---
    check("buffer_dir deleted after finalize", not layout.buffer_dir.exists())

finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n=== {passed} passed, {failed} failed ===")
import sys
sys.exit(0 if failed == 0 else 1)
