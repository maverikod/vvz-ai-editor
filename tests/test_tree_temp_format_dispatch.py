from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_TREE_TEMP,
    resolve_format_group,
)
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    serialize_tree_temp_roots,
)
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    parse_source_bytes_to_roots,
)
from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.dispatcher import HandlerDispatcher
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.commands.universal_file_edit.session import release_session
from tests.thin_editor_ca_mocks import open_ca_file, upstream_context
from ai_editor.core.file_handlers.registry import (
    HANDLER_INI,
    HANDLER_TOML,
    resolve_handler,
)


@pytest.mark.parametrize(
    ("suffix", "handler_id"),
    [(".ini", HANDLER_INI), (".cfg", HANDLER_INI), (".toml", HANDLER_TOML)],
)
def test_structured_config_suffixes_resolve_to_tree_temp(
    tmp_path: Path, suffix: str, handler_id: str
) -> None:
    source = tmp_path / f"settings{suffix}"

    assert resolve_handler(str(source), "read") == handler_id
    descriptor = resolve_format_group(source)
    assert descriptor.handler_id == handler_id
    assert descriptor.format_group == FORMAT_TREE_TEMP


@pytest.mark.parametrize(
    ("handler_id", "source", "expected"),
    [
        ("ini", b"name = editor\n", "name = editor\n"),
        ("toml", b'title = "editor"\n', 'title = "editor"\n'),
    ],
)
def test_generic_tree_temp_parse_and_serialize_dispatch(
    handler_id: str, source: bytes, expected: str
) -> None:
    roots = parse_source_bytes_to_roots(handler_id, source)

    assert roots
    assert serialize_tree_temp_roots(handler_id, roots) == expected


@pytest.mark.parametrize(
    ("suffix", "source"),
    [
        (".ini", "name = editor\n"),
        (".cfg", "[server]\nport = 8080\n"),
        (".toml", 'title = "editor"\n'),
    ],
)
def test_preview_dispatches_tree_temp_config_suffixes(
    tmp_path: Path, suffix: str, source: str
) -> None:
    path = tmp_path / f"settings{suffix}"
    path.write_text(source, encoding="utf-8")
    handler = HandlerDispatcher().dispatch(str(path))

    assert not isinstance(handler, PreviewError)
    result = navigate(
        handler,
        {
            "file_path": str(path),
            "project_id": "test-project",
            "node_ref": None,
            "selector": None,
        },
        PreviewBudget(
            preview_lines=20,
            value_preview_len=80,
            full_text_max_lines=0,
            max_chars=1000,
        ),
    )

    assert not isinstance(result, PreviewError)
    assert result.total_blocks > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "source"),
    [
        (".ini", "name = editor\n"),
        (".cfg", "[server]\nport = 8080\n"),
        (".toml", 'title = "editor"\n'),
    ],
)
async def test_create_then_preview_supports_tree_temp_config_suffixes(
    tmp_path: Path, suffix: str, source: str
) -> None:
    project_id = "d15ea5ed-1111-4111-8111-111111111111"
    rel = f"tmp/new{suffix}"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=project_id,
        file_path=rel,
        content=b"",
        create=True,
        initial_content=source,
    )
    try:
        with upstream_context(workspace=workspace, upstream=upstream):
            result = await UniversalFilePreviewCommand().execute(
                project_id=project_id,
                session_id=sid,
                file_path=rel,
            )
        assert isinstance(result, SuccessResult), result
        assert (result.data or {}).get("total_blocks", 0) > 0
    finally:
        release_session(sid, rel)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "source", "expected"),
    [
        (".ini", "first = 1\nthird = 3\n", "middle = 2"),
        (".toml", "first = 1\nthird = 3\n", "middle = 2"),
    ],
)
async def test_config_tree_temp_insert_commits_through_validation(
    tmp_path: Path,
    suffix: str,
    source: str,
    expected: str,
) -> None:
    from ai_editor.commands.universal_file_edit.edit_command import (
        UniversalFileEditCommand,
    )
    from tests.thin_editor_ca_mocks import commit_write

    project_id = "d15ea5ed-2222-4222-8222-222222222222"
    rel = f"tmp/settings{suffix}"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=project_id,
        file_path=rel,
        content=source.encode("utf-8"),
    )
    try:
        edit = UniversalFileEditCommand()
        with upstream_context(workspace=workspace, upstream=upstream):
            result = await edit.execute(
                **edit.validate_params(
                    {
                        "project_id": project_id,
                        "session_id": sid,
                        "file_path": rel,
                        "operations": [
                            {
                                "type": "insert",
                                "parent_json_pointer": "",
                                "key": "middle",
                                "value": "2" if suffix == ".ini" else 2,
                                "after_key": "first",
                            }
                        ],
                    }
                )
            )
        assert isinstance(result, SuccessResult), result
        commit = await commit_write(
            workspace=workspace,
            upstream=upstream,
            project_id=project_id,
            session_id=sid,
            file_path=rel,
        )
        assert commit.data["uploaded"] is True
        assert expected in origin.read_text(encoding="utf-8")
    finally:
        release_session(sid, rel)
