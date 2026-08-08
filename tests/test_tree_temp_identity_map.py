"""Tree-temp addressing: one identity map behind preview and edit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The defect these cover: ``universal_file_preview`` handed a caller an integer
``node_ref`` for a tree-temp document and ``universal_file_edit`` refused that
same integer, demanding a JSON Pointer or a stable UUID; and the integer was a
POSITION, so inserting anything above a node renumbered it. Both commands now
resolve through the session's ``TreeTempIdentityMap``, which binds the integer
to the node's ``stable_id`` through ``tree_engine``'s ShortIdMap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.core.json_tree import tree_builder as jtb
from ai_editor.core.tree_temp.identity import (
    TreeTempAddressError,
    TreeTempIdentityMap,
    bracket_pointer_to_rfc6901,
    key_path_to_rfc6901,
)
from ai_editor.core.tree_temp.json_source_parser import parse_json_source
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    open_ca_file,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_JSON_SRC = '{\n  "name": "probe",\n  "items": [10, 20],\n  "timeout": 30\n}\n'


@pytest.fixture(autouse=True)
def _reset_sessions() -> Any:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()


async def _preview(workspace: Path, upstream: object, rel: str, sid: str) -> dict:
    cmd = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(
            project_id=_PROJECT_UUID, file_path=rel, session_id=sid
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return dict(res.data or {})


async def _edit(
    workspace: Path, upstream: object, rel: str, sid: str, operations: list
) -> Any:
    cmd = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        return await cmd.execute(
            **cmd.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": operations,
                }
            )
        )


def _refs_by_pointer(envelope: dict) -> dict[str, int]:
    """``json_pointer`` -> reported ``node_ref``, for every previewed block."""
    out: dict[str, int] = {}
    for block in envelope.get("blocks") or []:
        summary = block.get("summary") or {}
        attributes = str(summary.get("attribute_summary") or "")
        marker = "json_pointer='"
        if marker not in attributes:
            continue
        pointer = attributes.split(marker, 1)[1].split("'", 1)[0]
        out[pointer] = block.get("node_ref")
    return out


def _draft(sid: str, rel: str) -> str:
    return get_session(sid, file_path=rel).draft_path.read_text(encoding="utf-8")


# -- the notation translation ------------------------------------------------


def test_bracket_pointer_translates_to_rfc6901() -> None:
    assert bracket_pointer_to_rfc6901("/items[0]") == "/items/0"
    assert bracket_pointer_to_rfc6901("/a[0][1]/b") == "/a/0/1/b"
    # Already canonical: RFC 6901 passes through untouched, which is what lets
    # one entry point take both declared forms.
    assert bracket_pointer_to_rfc6901("/items/0") == "/items/0"
    # Both spellings of the document root.
    assert bracket_pointer_to_rfc6901("") == ""
    assert bracket_pointer_to_rfc6901("/") == ""
    # Escapes belong to RFC 6901 and are left exactly as the caller wrote them.
    assert bracket_pointer_to_rfc6901("/a~1b") == "/a~1b"


def test_bracket_pointer_rejects_a_non_pointer() -> None:
    with pytest.raises(TreeTempAddressError):
        bracket_pointer_to_rfc6901("items/0")
    with pytest.raises(TreeTempAddressError):
        bracket_pointer_to_rfc6901(3)  # type: ignore[arg-type]


def test_key_path_translates_to_rfc6901() -> None:
    assert key_path_to_rfc6901("") == ""
    assert key_path_to_rfc6901("alpha") == "/alpha"
    assert key_path_to_rfc6901("gamma.inner") == "/gamma/inner"
    assert key_path_to_rfc6901("beta[1]") == "/beta/1"


# -- the map itself ----------------------------------------------------------


def test_every_address_form_names_the_same_node() -> None:
    identity = TreeTempIdentityMap().sync(parse_json_source(_JSON_SRC))
    by_pointer = identity.node("/items/0")
    assert by_pointer.value == 10
    short_id = identity.identifiers(by_pointer.stable_id).short_id
    assert identity.node(short_id) is by_pointer
    assert identity.node(str(short_id)) is by_pointer
    assert identity.node(by_pointer.stable_id) is by_pointer
    assert identity.node("/items[0]") is by_pointer


def test_reference_is_reported_in_the_engine_notation() -> None:
    roots = parse_json_source(_JSON_SRC)
    identity = TreeTempIdentityMap().sync(roots)
    identifiers = identity.identifiers("/items/1")
    assert identifiers.notation == "json_pointer"
    assert identifiers.ref == "/items/1"
    assert isinstance(identifiers.short_id, int)


def test_unknown_address_is_refused_not_guessed() -> None:
    identity = TreeTempIdentityMap().sync(parse_json_source(_JSON_SRC))
    for address in ("/nope", 9999, "not-a-uuid", "/items/9"):
        with pytest.raises(TreeTempAddressError):
            identity.node(address)


def test_integer_follows_the_node_not_its_position() -> None:
    roots = parse_json_source(_JSON_SRC)
    identity = TreeTempIdentityMap().sync(roots)
    timeout = identity.node("/timeout")
    before = identity.identifiers(timeout.stable_id).short_id
    root = roots[0]
    assert root.children is not None
    root.children.insert(0, parse_json_source('{"aaa": 0}')[0].children[0])
    identity.sync(roots)
    after = identity.identifiers(timeout.stable_id)
    assert after.short_id == before
    # The POINTER moved, which is what a pointer is for; the integer did not.
    assert after.ref == "/timeout"
    assert identity.node(before) is timeout


# -- preview and edit agree, end to end --------------------------------------


@pytest.mark.asyncio
async def test_preview_node_ref_is_accepted_by_edit(tmp_path: Path) -> None:
    rel = "cfg/tree.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_JSON_SRC.encode("utf-8"),
    )
    refs = _refs_by_pointer(await _preview(workspace, upstream, rel, sid))
    node_ref = refs["/name"]
    assert isinstance(node_ref, int)

    res = await _edit(
        workspace,
        upstream,
        rel,
        sid,
        [{"type": "replace", "node_ref": str(node_ref), "value": 90}],
    )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert json.loads(_draft(sid, rel))["name"] == 90


@pytest.mark.asyncio
async def test_preview_node_ref_survives_an_insert_above_it(tmp_path: Path) -> None:
    rel = "cfg/stable.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_JSON_SRC.encode("utf-8"),
    )
    before = _refs_by_pointer(await _preview(workspace, upstream, rel, sid))

    res = await _edit(
        workspace,
        upstream,
        rel,
        sid,
        [
            {
                "type": "insert",
                "parent_json_pointer": "",
                "key": "aaa",
                "before_key": "name",
                "value": 0,
            }
        ],
    )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)

    after = _refs_by_pointer(await _preview(workspace, upstream, rel, sid))
    assert after["/timeout"] == before["/timeout"]
    assert after["/items"] == before["/items"]
    assert after["/aaa"] not in before.values()

    # And the unchanged integer still edits the node it named before the insert.
    res = await _edit(
        workspace,
        upstream,
        rel,
        sid,
        [{"type": "replace", "node_ref": str(before["/timeout"]), "value": 61}],
    )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert json.loads(_draft(sid, rel))["timeout"] == 61


@pytest.mark.asyncio
async def test_both_declared_pointer_forms_reach_one_node(tmp_path: Path) -> None:
    rel = "cfg/pointers.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_JSON_SRC.encode("utf-8"),
    )
    for pointer, value in (("/items[0]", 11), ("/items/0", 12)):
        res = await _edit(
            workspace,
            upstream,
            rel,
            sid,
            [{"type": "replace", "json_pointer": pointer, "value": value}],
        )
        assert isinstance(res, SuccessResult), getattr(res, "message", res)
        assert json.loads(_draft(sid, rel))["items"][0] == value


@pytest.mark.asyncio
async def test_unknown_pointer_is_still_invalid_operation(tmp_path: Path) -> None:
    rel = "cfg/reject.json"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=_JSON_SRC.encode("utf-8"),
    )
    before = json.loads(_draft(sid, rel))
    res = await _edit(
        workspace,
        upstream,
        rel,
        sid,
        [{"type": "replace", "json_pointer": "/nope", "value": 1}],
    )
    assert isinstance(res, ErrorResult)
    assert res.code == "INVALID_OPERATION"
    # A rejection leaves the document as it was (the draft is re-serialized by
    # the rollback, so compare the data, not the whitespace).
    assert json.loads(_draft(sid, rel)) == before
