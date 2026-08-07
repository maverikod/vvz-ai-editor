"""Regression coverage for the parse-error fallback guards of universal_file_edit.

Before this fix the fallback bypassed every documented guard: an operation
addressing lines outside the draft, carrying mismatched anchors, naming an
unknown type, or using the forbidden Python sidecar form was reported as a
success and collapsed the draft to the operation's own content. Committing that
draft destroyed the file on disk for any format Code Analysis does not validate
on save (.toml among them).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.errors import (
    ANCHOR_MISMATCH,
    INVALID_OPERATION,
    LINE_OUT_OF_RANGE,
    UNKNOWN_NODE_REF,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.commands.universal_file_edit.text_fallback_tree import (
    BLANK,
    PARAGRAPH,
    FallbackDocumentTree,
)
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_BROKEN = "x = 1\ny = 2\nz = 3\ndef broken(:\n"


@pytest.fixture(autouse=True)
def _reset_sessions() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    for rel in ("broken.py", "damage.py"):
        reset_ca_session(DEFAULT_CA_SESSION_ID, rel)
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)


async def _fallback_session(tmp_path: Path, content: str = _BROKEN):
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path="broken.py",
        content=content.encode("utf-8"),
    )
    return sid, workspace, origin, upstream


async def _edit(sid: str, workspace, upstream, operations: List[Dict[str, Any]]):
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        return await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path="broken.py",
            operations=operations,
        )


def _draft_text(sid: str) -> str:
    return get_session(sid).draft_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The tree itself
# --------------------------------------------------------------------------


def test_every_line_is_a_node_of_the_tree() -> None:
    tree = FallbackDocumentTree.from_source("a\nb\n\nc\n")
    assert tree.line_count == 4
    assert [n.start_line for n in tree.line_nodes] == [1, 2, 3, 4]
    # Zero-based node_ref addresses the i-th line node.
    assert tree.line_node(0).start_line == 1
    assert tree.line_node(3).start_line == 4
    assert tree.line_node(4) is None


def test_blocks_alternate_paragraph_and_blank() -> None:
    tree = FallbackDocumentTree.from_source("a\nb\n\n\nc\n")
    assert [(b.kind, b.start_line, b.end_line) for b in tree.blocks] == [
        (PARAGRAPH, 1, 2),
        (BLANK, 3, 4),
        (PARAGRAPH, 5, 5),
    ]
    assert tree.block_at_line(3).kind == BLANK
    assert tree.block_at_line(99) is None


def test_root_spans_the_whole_document() -> None:
    tree = FallbackDocumentTree.from_source("a\nb\nc\n")
    assert tree.root.line_span == (1, 3)
    assert tree.covers(1, 3) is True
    assert tree.covers(1, 4) is False
    assert tree.covers(0, 1) is False
    # end-of-document is an insert position, not a line node
    assert tree.accepts_insert_at(4) is True
    assert tree.accepts_insert_at(5) is False


# --------------------------------------------------------------------------
# The guards, through the real command
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_range_line_is_refused_and_draft_untouched(
    tmp_path: Path,
) -> None:
    """The exact reported vector: start_line far past the end of the draft."""
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    assert get_session(sid).is_invalid is True
    before = _draft_text(sid)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [{"type": "replace", "start_line": 400, "end_line": 400, "content": "oops = 9\n"}],
    )
    assert isinstance(result, ErrorResult)
    assert result.code == LINE_OUT_OF_RANGE
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_anchor_mismatch_is_refused_and_draft_untouched(tmp_path: Path) -> None:
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    before = _draft_text(sid)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [
            {
                "type": "replace",
                "start_line": 1,
                "end_line": 1,
                "content": "w",
                "anchor_head": "ZZZZZ",
                "anchor_tail": "ZZZZZ",
            }
        ],
    )
    assert isinstance(result, ErrorResult)
    assert result.code == ANCHOR_MISMATCH
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_unknown_operation_type_is_refused_in_fallback(tmp_path: Path) -> None:
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    before = _draft_text(sid)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [{"type": "frobnicate", "start_line": 1, "content": "w"}],
    )
    assert isinstance(result, ErrorResult)
    assert result.code == INVALID_OPERATION
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_sidecar_node_form_is_forbidden_in_fallback(tmp_path: Path) -> None:
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    before = _draft_text(sid)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [{"type": "replace", "node_id": "1", "code_lines": ["x = 1"]}],
    )
    assert isinstance(result, ErrorResult)
    assert result.code == INVALID_OPERATION
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_unknown_node_ref_is_refused_in_fallback(tmp_path: Path) -> None:
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    before = _draft_text(sid)
    result = await _edit(
        sid, workspace, upstream, [{"type": "replace", "node_ref": "nope", "content": "q"}]
    )
    assert isinstance(result, ErrorResult)
    assert result.code == UNKNOWN_NODE_REF
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_rejected_batch_does_not_half_apply(tmp_path: Path) -> None:
    """A valid operation batched with a refused one must not be applied."""
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    before = _draft_text(sid)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [
            {"type": "replace", "start_line": 1, "end_line": 1, "content": "GOOD\n"},
            {"type": "replace", "start_line": 400, "end_line": 400, "content": "BAD\n"},
        ],
    )
    assert isinstance(result, ErrorResult)
    assert result.code == LINE_OUT_OF_RANGE
    assert _draft_text(sid) == before
    assert "GOOD" not in _draft_text(sid)


# --------------------------------------------------------------------------
# The fallback must remain usable
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_range_replace_still_applies_precisely(tmp_path: Path) -> None:
    """A legitimate line edit must change only the line it addresses."""
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    result = await _edit(
        sid,
        workspace,
        upstream,
        [{"type": "replace", "start_line": 4, "end_line": 4, "content": "def fixed():\n"}],
    )
    assert isinstance(result, SuccessResult)
    assert _draft_text(sid) == "x = 1\ny = 2\nz = 3\ndef fixed():\n"


@pytest.mark.asyncio
async def test_insert_and_delete_still_apply_in_fallback(tmp_path: Path) -> None:
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    assert isinstance(
        await _edit(
            sid, workspace, upstream, [{"type": "insert", "start_line": 1, "content": "top = 0"}]
        ),
        SuccessResult,
    )
    assert isinstance(
        await _edit(
            sid, workspace, upstream, [{"type": "delete", "start_line": 2, "end_line": 2}]
        ),
        SuccessResult,
    )
    assert _draft_text(sid) == "top = 0\ny = 2\nz = 3\ndef broken(:\n"


@pytest.mark.asyncio
async def test_insert_at_end_of_document_is_accepted(tmp_path: Path) -> None:
    """line_count + 1 is the root's tail boundary and must stay addressable."""
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    result = await _edit(
        sid, workspace, upstream, [{"type": "insert", "start_line": 5, "content": "tail = 1"}]
    )
    assert isinstance(result, SuccessResult)
    assert _draft_text(sid).endswith("def broken(:\ntail = 1\n")


@pytest.mark.asyncio
async def test_root_node_ref_replaces_the_whole_document(tmp_path: Path) -> None:
    """node_ref "" addresses the document root and still rewrites the file."""
    sid, workspace, origin, upstream = await _fallback_session(tmp_path)
    fixed = "x = 1\ny = 2\nz = 3\ndef fixed():\n    pass\n"
    result = await _edit(
        sid, workspace, upstream, [{"type": "replace", "node_ref": "", "content": fixed}]
    )
    assert isinstance(result, SuccessResult)
    assert _draft_text(sid) == fixed
    wr = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path="broken.py",
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert origin.read_text(encoding="utf-8") == fixed


@pytest.mark.asyncio
async def test_unknown_operation_type_is_refused_on_normal_text(
    tmp_path: Path,
) -> None:
    """Same defect class off the fallback: an unknown type was applied as a replace."""
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path="broken.py",
        content=b"alpha\nbeta\ngamma\n",
    )
    session = get_session(sid)
    assert session.is_invalid is False
    before = _draft_text(sid)
    result = await _edit(
        sid, workspace, upstream, [{"type": "frobnicate", "start_line": 1, "content": "w"}]
    )
    assert isinstance(result, ErrorResult)
    assert result.code == INVALID_OPERATION
    assert _draft_text(sid) == before


@pytest.mark.asyncio
async def test_numeric_node_ref_addresses_the_matching_line_node(
    tmp_path: Path,
) -> None:
    """Zero-based node_ref is the i-th line node of the fallback tree."""
    sid, workspace, _origin, upstream = await _fallback_session(tmp_path)
    result = await _edit(
        sid, workspace, upstream, [{"type": "replace", "node_ref": "1", "content": "y = 22\n"}]
    )
    assert isinstance(result, SuccessResult)
    assert _draft_text(sid) == "x = 1\ny = 22\nz = 3\ndef broken(:\n"
