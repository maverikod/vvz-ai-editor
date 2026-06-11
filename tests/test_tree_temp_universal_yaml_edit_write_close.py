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
