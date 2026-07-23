"""YAML tree-temp integration for universal_file_open/edit/write/close.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.core.yaml_tree import tree_builder as ytb
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    commit_write,
    materialize_tree_sidecar,
    open_ca_file,
    reset_ca_session,
    upstream_context,
)

_YAML_PROJECT_UUID = "d00dfeed-d00d-4d00-d00d-feedd00dfe1"
_REL = "records/stack.yml"
_BODY = b"""items:
  - id: 1
    active: false
meta:
  tag: old  # lbl
# eof
"""


def _clear() -> None:
    ytb._trees.clear()


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    _clear()
    yield
    reset_ca_session(DEFAULT_CA_SESSION_ID, _REL)
    _clear()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _prep(
    tmp: Path, rel: str = _REL, content: bytes = _BODY
) -> tuple[str, Path, Path, object]:
    return await open_ca_file(
        tmp,
        project_id=_YAML_PROJECT_UUID,
        file_path=rel,
        content=content,
    )


@pytest.mark.asyncio
async def test_yaml_replace_via_json_pointer_updates_then_commits(
    tmp_path: Path,
) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/items/0/active",
                            "value": True,
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    data = yaml.safe_load(origin.read_text(encoding="utf-8"))
    assert data["items"][0]["active"] is True
    sc = materialize_tree_sidecar(origin, file_path=_REL)
    sections = parse_tree_file(sc.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == _sha(origin.read_bytes())
    assert sections.tree.strip() != ""
    assert sections.map.next_free >= 1
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_delete_meta_tag(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [{"type": "delete", "json_pointer": "/meta/tag"}],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    data = yaml.safe_load(origin.read_text(encoding="utf-8"))
    assert "tag" not in data.get("meta", {})
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_insert_array_appends(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/items",
                            "value": {"id": 2, "active": True},
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    data = yaml.safe_load(origin.read_text(encoding="utf-8"))
    assert len(data["items"]) == 2
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_object_insert_after_key(tmp_path: Path) -> None:
    rel = "records/yorder.yml"
    body = b"first: 1\nthird: 3\n"
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, body)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "second",
                            "value": 2,
                            "after_key": "first",
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    data = yaml.safe_load(origin.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["first", "second", "third"]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


async def _insert_yaml_root_key_and_preview(
    tmp_path: Path,
    *,
    rel: str,
    operation: dict[str, object],
) -> tuple[str, object]:
    body = b"first: 1\nthird: 3\n"
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, body)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [operation],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult)
        assert edit_res.data.get("updated") is True
        preview_res = await preview.execute(
            **preview.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                }
            )
        )
    assert isinstance(preview_res, SuccessResult)
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    committed_text = origin.read_text(encoding="utf-8")
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
    return committed_text, preview_res


@pytest.mark.asyncio
async def test_yaml_root_key_insert_with_empty_parent_pointer(
    tmp_path: Path,
) -> None:
    committed_text, preview_res = await _insert_yaml_root_key_and_preview(
        tmp_path,
        rel="records/root_empty_parent.yml",
        operation={
            "type": "insert",
            "parent_json_pointer": "",
            "key": "second",
            "value": 2,
        },
    )
    data = yaml.safe_load(committed_text)
    assert data == {"first": 1, "third": 3, "second": 2}
    assert "second" in str(preview_res.data)


@pytest.mark.asyncio
async def test_yaml_root_key_insert_with_slash_parent_pointer(
    tmp_path: Path,
) -> None:
    committed_text, preview_res = await _insert_yaml_root_key_and_preview(
        tmp_path,
        rel="records/root_slash_parent.yml",
        operation={
            "type": "insert",
            "parent_json_pointer": "/",
            "key": "second",
            "value": 2,
        },
    )
    data = yaml.safe_load(committed_text)
    assert data == {"first": 1, "third": 3, "second": 2}
    assert "second" in str(preview_res.data)


@pytest.mark.asyncio
async def test_yaml_batch_invalid_first_operation(tmp_path: Path) -> None:
    sid, workspace, origin, upstream = await _prep(tmp_path)
    h0 = _sha(origin.read_bytes())
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        out = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/nope"},
                        {"type": "replace", "json_pointer": "/items/0/id", "value": 9},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha(origin.read_bytes()) == h0


@pytest.mark.asyncio
async def test_yaml_replace_one_element_list_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion A: replace with one-element list of dicts stays a YAML sequence."""
    rel = "records/single_seq.yml"
    sid, workspace, origin, upstream = await _prep(
        tmp_path, rel, b"source_ranges: []\n"
    )
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [{"start": 1336, "end": 1353}],
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    text = origin.read_text(encoding="utf-8")
    assert "\n- " in text or text.strip().startswith("- ")
    data = yaml.safe_load(text)
    assert isinstance(data["source_ranges"], list)
    assert data["source_ranges"] == [{"start": 1336, "end": 1353}]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_replace_one_element_scalar_list_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion B: replace with one-element scalar list stays a sequence."""
    rel = "records/scalar_seq.yml"
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, b"tags: []\n")
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/tags",
                            "value": ["x"],
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    text = origin.read_text(encoding="utf-8")
    assert "- x" in text or "- 'x'" in text or '- "x"' in text
    data = yaml.safe_load(text)
    assert isinstance(data["tags"], list)
    assert data["tags"] == ["x"]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_insert_one_element_list_into_mapping_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion C: insert one-element list value under a mapping key."""
    rel = "records/insert_seq.yml"
    sid, workspace, origin, upstream = await _prep(
        tmp_path, rel, b"meta:\n  tag: old\n"
    )
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "items",
                            "value": [{"a": 1}],
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    text = origin.read_text(encoding="utf-8")
    assert "- a:" in text or "\n- " in text
    data = yaml.safe_load(text)
    assert isinstance(data["items"], list)
    assert data["items"] == [{"a": 1}]
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


@pytest.mark.asyncio
async def test_yaml_top_level_one_element_list_roundtrips_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion F: replacing a multi-item list with one item stays a YAML sequence."""
    rel = "records/top_level_seq.yml"
    body = (
        b"source_ranges:\n"
        b"  - start: 1\n"
        b"    end: 2\n"
        b"  - start: 3\n"
        b"    end: 4\n"
    )
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, body)
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [{"start": 1336, "end": 1353}],
                        }
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    text = origin.read_text(encoding="utf-8")
    assert "\n- " in text
    data = yaml.safe_load(text)
    assert isinstance(data["source_ranges"], list)
    assert len(data["source_ranges"]) == 1
    assert data["source_ranges"][0] == {"start": 1336, "end": 1353}
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )


_45B27A37_BODY = b"""# banner line 1
# banner line 2
name: "abc-123"  # inline comment
single: 'single-quoted'
flow: { a: 1, b: 2 }
second: value2  # second inline
"""


@pytest.mark.asyncio
async def test_45b27a37_yaml_create_zero_edit_commit_is_byte_identical(
    tmp_path: Path,
) -> None:
    """Bug 45b27a37: create=True + zero edits must commit initial_content verbatim.

    No comment stripping, no quote normalization, no flow-to-block expansion:
    the committed bytes must equal ``initial_content`` exactly.
    """
    rel = "45b27a37_create.yml"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    from tests.thin_editor_ca_mocks import (
        ensure_projectid_marker,
        layout_origin,
        mock_upstream,
        session_dir_for,
    )
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )

    upstream = mock_upstream()
    sid = DEFAULT_CA_SESSION_ID
    reset_ca_session(sid, rel)
    with upstream_context(workspace=workspace, upstream=upstream):
        cmd = UniversalFileOpenCommand()
        res = await cmd.execute(
            **cmd.validate_params(
                {
                    "session_id": sid,
                    "project_id": _YAML_PROJECT_UUID,
                    "file_path": rel,
                    "create": True,
                    "initial_content": _45B27A37_BODY.decode("utf-8"),
                }
            )
        )
        assert isinstance(res, SuccessResult), res
    ensure_projectid_marker(session_dir_for(workspace, sid, _YAML_PROJECT_UUID, rel), _YAML_PROJECT_UUID)
    origin = layout_origin(workspace, sid, _YAML_PROJECT_UUID, rel)

    commit_res = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    assert commit_res.data["uploaded"] is True
    committed = origin.read_bytes()
    assert committed == _45B27A37_BODY, (
        f"zero-edit create commit must be byte-identical to initial_content; "
        f"got:\n{committed.decode('utf-8', 'replace')!r}"
    )
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid, "file_path": rel}
            )
        )


@pytest.mark.asyncio
async def test_45b27a37_yaml_existing_file_zero_edit_commit_is_noop(
    tmp_path: Path,
) -> None:
    """Bug 45b27a37 sibling case: opening an EXISTING file with zero edits and
    committing must not rewrite it at all (no upload, byte-identical origin).
    """
    rel = "records/45b27a37_existing.yml"
    sid, workspace, origin, upstream = await _prep(tmp_path, rel, _45B27A37_BODY)
    pre_bytes = origin.read_bytes()
    assert pre_bytes == _45B27A37_BODY

    commit_res = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    assert commit_res.data["uploaded"] is False
    assert commit_res.data["unchanged"] is True
    committed = origin.read_bytes()
    assert committed == _45B27A37_BODY, (
        f"zero-edit no-op commit on an existing file must not rewrite it; "
        f"got:\n{committed.decode('utf-8', 'replace')!r}"
    )
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid, "file_path": rel}
            )
        )


_B215FBD3_BODY = (
    "# banner comment\n"
    'name: "abc-123"  # inline comment\n'
    "flow_map: { a: 1, b: 2 }\n"
    "flow_list: [1, 2, 3]\n"
    "target: old\n"
)


@pytest.mark.asyncio
async def test_b215fbd3_yaml_create_then_edit_commit_preserves_style(
    tmp_path: Path,
) -> None:
    """Bug b215fbd3 (live path): create=True + one tree-temp mutation + commit
    must preserve style on every UNTOUCHED node — banner comment, inline
    comment, quoted scalar, flow-map style (padding-only tolerance), and
    flow-list style — while applying the mutated node's new value.

    Reproduces the live universal_file_open(create=true) -> edit_batch ->
    write(commit) pipeline through the real session/command machinery
    (not the bare parse/mutate/serialize helpers), so it also exercises
    whichever branch of ``serialize_tree_temp_session_source`` actually
    fires for a mutated create=True tree-temp session.
    """
    rel = "b215fbd3_create_edit.yml"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    from tests.thin_editor_ca_mocks import (
        ensure_projectid_marker,
        layout_origin,
        mock_upstream,
        session_dir_for,
    )
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )

    upstream = mock_upstream()
    sid = DEFAULT_CA_SESSION_ID
    reset_ca_session(sid, rel)
    with upstream_context(workspace=workspace, upstream=upstream):
        open_res = await UniversalFileOpenCommand().execute(
            **UniversalFileOpenCommand().validate_params(
                {
                    "session_id": sid,
                    "project_id": _YAML_PROJECT_UUID,
                    "file_path": rel,
                    "create": True,
                    "initial_content": _B215FBD3_BODY,
                }
            )
        )
        assert isinstance(open_res, SuccessResult), open_res
    ensure_projectid_marker(
        session_dir_for(workspace, sid, _YAML_PROJECT_UUID, rel), _YAML_PROJECT_UUID
    )
    origin = layout_origin(workspace, sid, _YAML_PROJECT_UUID, rel)

    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/target",
                            "value": "new",
                        }
                    ],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult), edit_res

    commit_res = await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    assert commit_res.data["uploaded"] is True
    committed = origin.read_text(encoding="utf-8")

    data = yaml.safe_load(committed)
    assert data["target"] == "new"

    assert "# banner comment" in committed, committed
    assert 'name: "abc-123"' in committed, committed
    assert "# inline comment" in committed, committed
    flow_map_line = next(
        (line for line in committed.splitlines() if line.startswith("flow_map:")),
        "",
    )
    assert flow_map_line.strip().startswith("flow_map: {"), committed
    assert flow_map_line.rstrip().endswith("}"), committed
    flow_list_line = next(
        (line for line in committed.splitlines() if line.startswith("flow_list:")),
        "",
    )
    assert flow_list_line.strip() == "flow_list: [1, 2, 3]", committed

    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid, "file_path": rel}
            )
        )


@pytest.mark.asyncio
async def test_yaml_empty_list_and_dict_roundtrip(tmp_path: Path) -> None:
    """Criterion G: empty list and empty dict preserve container types."""
    rel = "records/empty_containers.yml"
    sid, workspace, origin, upstream = await _prep(
        tmp_path, rel, b"items:\n  - id: 1\nslots: {}\n"
    )
    ed = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "replace", "json_pointer": "/items", "value": []},
                        {"type": "replace", "json_pointer": "/slots", "value": {}},
                    ],
                }
            )
        )
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_YAML_PROJECT_UUID,
        session_id=sid,
    )
    data = yaml.safe_load(origin.read_text(encoding="utf-8"))
    assert isinstance(data["items"], list)
    assert data["items"] == []
    assert isinstance(data["slots"], dict)
    assert data["slots"] == {}
    with upstream_context(workspace=workspace, upstream=upstream):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
