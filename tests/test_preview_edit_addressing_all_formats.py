"""
Preview node_ref must resolve consistently in universal_file_edit (all formats).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
    run_sidecar_cst_edit_batch,
)
from ai_editor.commands.universal_file_preview import UniversalFilePreviewCommand
from ai_editor.core.cst_tree.tree_builder import (
    get_tree,
    load_file_to_tree,
    remove_tree,
)
from ai_editor.core.json_tree import tree_builder as jtb
from tests.fixtures.validation_passing_python import BAR_INSERT_LINES, MOD_WITH_FOO
from tests.thin_editor_ca_mocks import (
    DEFAULT_CA_SESSION_ID,
    clear_ca_session,
    commit_write,
    open_ca_file,
    upstream_context,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


async def _run_inline(func: Any, *args: Any, **kwargs: Any) -> Any:
    return func(*args, **kwargs)


async def _open_file(
    tmp: Path, rel: str, content: str
) -> tuple[str, Path, Path, object]:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    return await open_ca_file(
        tmp,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=content.encode("utf-8"),
    )


async def _preview_blocks(
    workspace: Path,
    upstream: object,
    rel: str,
    *,
    session_id: str | None = None,
) -> list[dict]:
    cmd = UniversalFilePreviewCommand()
    params: dict[str, Any] = {"project_id": _PROJECT_UUID, "file_path": rel}
    if session_id is not None:
        params["session_id"] = session_id
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    blocks = list((res.data or {}).get("blocks") or [])
    if blocks:
        return blocks
    if session_id is None:
        return blocks
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await cmd.execute(project_id=_PROJECT_UUID, file_path=rel)
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return list((res.data or {}).get("blocks") or [])


def _block_short_id(block: dict) -> str:
    ref = block.get("node_ref")
    if isinstance(ref, int):
        return str(ref)
    return str(ref).strip()


def _find_block_by_key_path(blocks: list[dict], key: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"key_path='{key}'" in attrs or f'key_path="{key}"' in attrs:
            return block
    raise AssertionError(f"no block for key {key!r} in {blocks!r}")


def _find_block_by_type(blocks: list[dict], node_type: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == node_type:
            return block
    raise AssertionError(f"no block with type {node_type!r} in {blocks!r}")


def _find_block_containing_text(blocks: list[dict], text: str) -> dict:
    for block in blocks:
        if text in str(block.get("text") or ""):
            return block
    raise AssertionError(f"no block containing {text!r} in {blocks!r}")


def _find_block_by_json_pointer(blocks: list[dict], pointer: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"json_pointer='{pointer}'" in attrs:
            return block
    raise AssertionError(f"no block for pointer {pointer!r} in {blocks!r}")


async def _commit(
    workspace: Path, upstream: object, sid: str, origin: Path, rel: str
) -> str:
    await commit_write(
        workspace=workspace,
        upstream=upstream,
        project_id=_PROJECT_UUID,
        session_id=sid,
        file_path=rel,
    )
    text = origin.read_text(encoding="utf-8")
    close = UniversalFileCloseCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        await close.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            file_path=rel,
        )
    return text


async def _preview_diff(workspace: Path, upstream: object, sid: str, rel: str) -> str:
    write = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "write_mode": "preview",
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    assert res.data.get("phase") == "preview"
    assert res.data.get("has_changes") is True
    diff = res.data.get("diff")
    assert isinstance(diff, str) and diff
    return diff


@pytest.fixture(autouse=True)
def _reset_json_trees() -> None:
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()
    yield
    clear_ca_session(DEFAULT_CA_SESSION_ID)
    jtb._trees.clear()


@pytest.mark.asyncio
async def test_json_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "data/doc.json"
    body = '{"items": [{"id": 1}], "meta": {"tag": "old"}}\n'
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    meta_block = _find_block_by_json_pointer(blocks, "/meta")
    meta_sid = _block_short_id(meta_block)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": meta_sid,
                            "position": "before",
                            "key": "note",
                            "value": "inserted",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    data = json.loads(text)
    keys = list(data.keys())
    assert keys.index("note") < keys.index("meta")
    assert data["note"] == "inserted"


@pytest.mark.asyncio
async def test_yaml_insert_by_preview_short_id_node_ref(tmp_path: Path) -> None:
    rel = "cfg/app.yaml"
    body = "alpha: 1\nbeta: 2\n"
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    beta_sid = _block_short_id(_find_block_by_key_path(blocks, "beta"))

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": beta_sid,
                            "position": "before",
                            "key": "middle",
                            "value": 99,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert text.index("middle:") < text.index("beta:")


@pytest.mark.asyncio
async def test_txt_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "notes/readme.txt"
    body = "First paragraph line.\n\nSecond paragraph line.\n"
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    second_sid = _block_short_id(
        next(b for b in blocks if int(_block_short_id(b)) >= 2)
    )

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": second_sid,
                            "position": "before",
                            "content": "Inserted between paragraphs.\n",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert "Inserted between paragraphs." in text
    assert text.index("First paragraph") < text.index("Inserted between")
    assert text.index("Inserted between") < text.index("Second paragraph")


@pytest.mark.asyncio
async def test_jsonl_insert_by_preview_line_index_node_ref(tmp_path: Path) -> None:
    rel = "streams/events.jsonl"
    body = '{"event": "one"}\n{"event": "two"}\n'
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    line_ref = next(
        str(b["node_ref"]) for b in blocks if str(b.get("node_ref")) in ("1", 1)
    )

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": line_ref,
                            "position": "before",
                            "content": '{"event": "middle"}\n',
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[1] == '{"event": "middle"}'


@pytest.mark.asyncio
async def test_py_insert_by_preview_short_id_target_node_id(tmp_path: Path) -> None:
    rel = "src/mod.py"
    body = MOD_WITH_FOO
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    func_sid = _block_short_id(_find_block_by_type(blocks, "function"))

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": func_sid,
                            "position": "before",
                            "code_lines": BAR_INSERT_LINES,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert text.index("def bar") < text.index("def foo")


@pytest.mark.asyncio
async def test_py_insert_into_class_preserves_header_comment(tmp_path: Path) -> None:
    rel = "src/header_comment.py"
    body = (
        '"""Class insert comment fixture."""\n\n'
        "class Foo:  # type: ignore[misc]\n"
        '    """Fixture class."""\n\n'
        "    def existing(self) -> int:\n"
        '        """Return one."""\n'
        "        return 1\n"
    )
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    class_sid = _block_short_id(_find_block_by_type(blocks, "class"))

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_node_id": class_sid,
                            "position": "last",
                            "code_lines": [
                                "",
                                "def added(self) -> int:",
                                '    """Return two."""',
                                "    return 2",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    class_header = next(
        line for line in text.splitlines() if line.startswith("class Foo")
    )
    assert "# type: ignore[misc]" in class_header
    assert text.index("    def added") > text.index("class Foo")
    assert "\ndef added" not in text


def test_py_sidecar_edit_preserves_declaration_trivia(tmp_path: Path) -> None:
    """Regression: editor CST replacements retain declaration source trivia."""
    path = tmp_path / "trivia.py"
    body = (
        '"""CST declaration trivia fixture."""\n'
        "from __future__ import annotations\n\n"
        "# class header\n"
        "class C:  # class trailing\n"
        "    pass  # type: ignore\n\n"
        "# def header\n"
        "def f():  # def trailing\n"
        "    return 1  # pragma: no cover\n\n"
        "# async header\n"
        "async def af():  # async trailing\n"
        "    return 2  # type: ignore\n\n"
        "# neighbor header\n"
        "def neighbor():  # neighbor trailing\n"
        "    pass  # pragma: no cover\n"
    )
    path.write_text(body, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    session = create_session(
        path,
        resolve_format_group(path),
        file_path=path.name,
        tree_id=tree.tree_id,
        ca_session_id="test-ca-trivia",
    )
    try:
        stable_ids = {
            metadata.name: metadata.stable_id
            for metadata in tree.metadata_map.values()
            if metadata.type in ("ClassDef", "FunctionDef")
            and metadata.name in ("C", "f", "af", "neighbor")
        }
        result = run_sidecar_cst_edit_batch(
            session,
            [
                {
                    "type": "replace",
                    "node_id": stable_ids["C"],
                    "code_lines": ["class C2:", "    pass"],
                },
                {
                    "type": "replace",
                    "node_id": stable_ids["f"],
                    "code_lines": ["def f():", "    return 11"],
                },
                {
                    "type": "replace",
                    "node_id": stable_ids["af"],
                    "code_lines": ["async def af():", "    return 22"],
                },
            ],
        )
        assert isinstance(result, SuccessResult), result
        updated = get_tree(session.tree_id)
        assert updated is not None
        source = updated.module.code
        for marker in (
            "# class header",
            "# class trailing",
            "# def header",
            "# def trailing",
            "# async header",
            "# async trailing",
            "# neighbor header",
            "# neighbor trailing",
            "# type: ignore",
            "# pragma: no cover",
        ):
            assert marker in source
        assert "class C2:" in source
        assert "return 11" in source
        assert "return 22" in source
    finally:
        release_session(session.session_id)
        remove_tree(tree.tree_id)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_py_preview_edit_addresses_try_except_statement_region(
    tmp_path: Path,
) -> None:
    """API-contract regression: try/except body statements stay addressable."""
    rel = "src/try_region.py"
    body = (
        '"""Try/except addressing fixture."""\n\n'
        "try:\n"
        '    print("risky()")\n'
        "except ValueError:\n"
        '    print("handle()")\n'
    )
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
    handle_ref = _block_short_id(_find_block_containing_text(blocks, "handle()"))

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": handle_ref,
                            "position": "before",
                            "code_lines": ['print("log_value_error()")'],
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(workspace, upstream, sid, origin, rel)
    assert "except ValueError:" in text
    assert "log_value_error()" in text
    assert "handle()" in text


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_py_create_search_replace_preview_preserves_omitted_declaration_trivia(
    tmp_path: Path,
) -> None:
    rel = "src/live_86288c9c.py"
    body = "class Foo:  # type: ignore[misc]\n    pass  # keep body note\n"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b"",
        create=True,
        initial_content=body,
    )

    search = UniversalFileSearchCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        sr = await search.execute(
            **search.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "search_type": "simple",
                    "node_type": "ClassDef",
                    "name": "Foo",
                    "require_one": True,
                }
            )
        )
    assert isinstance(sr, SuccessResult), getattr(sr, "message", sr)

    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        er = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": sr.data["node_ref"],
                            "code_lines": [
                                "class Foo:",
                                "    def value(self) -> int:",
                                "        return 2",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(er, SuccessResult), getattr(er, "message", er)

    diff = await _preview_diff(workspace, upstream, sid, rel)
    assert "-class Foo:  # type: ignore[misc]" not in diff
    assert "+class Foo:" not in diff
    assert "+    def value(self) -> int:" in diff
    assert "# keep body note" in diff


@pytest.mark.asyncio
async def test_json_unknown_node_ref_not_silent_success(tmp_path: Path) -> None:
    rel = "data/x.json"
    sid, workspace, _origin, upstream = await _open_file(tmp_path, rel, '{"a": 1}\n')
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": "99999",
                            "position": "before",
                            "key": "z",
                            "value": 0,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code in ("UNKNOWN_NODE_REF", "INVALID_OPERATION")


@pytest.mark.asyncio
async def test_yaml_structured_edit_preview_diff_covers_root_operations(
    tmp_path: Path,
) -> None:
    rel = "cfg/app.yaml"
    body = "alpha: 1\nkeep: true\nbeta: 2\n"
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "inserted",
                            "value": 3,
                            "after_key": "alpha",
                        },
                        {
                            "type": "replace",
                            "json_pointer": "/alpha",
                            "value": 10,
                        },
                        {"type": "delete", "json_pointer": "/beta"},
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    diff = await _preview_diff(workspace, upstream, sid, rel)
    assert "+inserted: 3" in diff
    assert "-alpha: 1" in diff
    assert "+alpha: 10" in diff
    assert "-beta: 2" in diff
    assert " keep: true" in diff
    release_session(sid, rel)


@pytest.mark.asyncio
async def test_ini_structured_edit_preview_diff_covers_root_and_section_keys(
    tmp_path: Path,
) -> None:
    rel = "cfg/app.ini"
    body = (
        "; preamble\n"
        "root = old\n"
        "keep = yes ; keep root\n"
        "\n"
        "[server] ; section\n"
        "# keep host comment\n"
        "host: localhost\n"
        "port: 80\n"
    )
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "added",
                            "value": "new",
                            "after_key": "root",
                        },
                        {
                            "type": "replace",
                            "json_pointer": "/root",
                            "value": "updated",
                        },
                        {"type": "delete", "json_pointer": "/server/port"},
                        {
                            "type": "insert",
                            "parent_json_pointer": "/server",
                            "key": "timeout",
                            "value": "30",
                        },
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    diff = await _preview_diff(workspace, upstream, sid, rel)
    assert "+added = new" in diff
    assert "-root = old" in diff
    assert "+root = updated" in diff
    assert "-port: 80" in diff
    assert "+timeout: 30" in diff
    assert " keep = yes ; keep root" in diff
    assert " [server] ; section" in diff
    assert " # keep host comment" in diff
    release_session(sid, rel)


@pytest.mark.asyncio
async def test_toml_structured_edit_preview_diff_covers_root_and_table_keys(
    tmp_path: Path,
) -> None:
    rel = "cfg/app.toml"
    body = (
        "# root comment\n"
        'title = "old"\n'
        "keep = true # keep root\n"
        "\n"
        "[server] # table\n"
        "# keep host comment\n"
        'host = "localhost"\n'
        "port = 80\n"
    )
    sid, workspace, origin, upstream = await _open_file(tmp_path, rel, body)
    edit = UniversalFileEditCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "file_path": rel,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "added",
                            "value": "new",
                            "after_key": "title",
                        },
                        {
                            "type": "replace",
                            "json_pointer": "/title",
                            "value": "updated",
                        },
                        {"type": "delete", "json_pointer": "/server/port"},
                        {
                            "type": "insert",
                            "parent_json_pointer": "/server",
                            "key": "enabled",
                            "value": True,
                        },
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    diff = await _preview_diff(workspace, upstream, sid, rel)
    assert '+added = "new"' in diff
    assert '-title = "old"' in diff
    assert '+title = "updated"' in diff
    assert "-port = 80" in diff
    assert "+enabled = true" in diff
    assert " keep = true # keep root" in diff
    assert " [server] # table" in diff
    assert " # keep host comment" in diff
    release_session(sid, rel)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "source", "replacement", "diff_marker"),
    [
        (".ini", "name = before\n", "after", "+name = after"),
        (".toml", 'title = "before"\n', "after", '+title = "after"'),
    ],
)
async def test_tree_temp_preview_node_ref_edits_create_draft_and_write_preview(
    tmp_path: Path,
    suffix: str,
    source: str,
    replacement: str,
    diff_marker: str,
) -> None:
    """A config preview UUID is a valid edit target in the same session."""
    rel = f"cfg/new{suffix}"
    sid, workspace, _origin, upstream = await open_ca_file(
        tmp_path,
        project_id=_PROJECT_UUID,
        file_path=rel,
        content=b"",
        create=True,
        initial_content=source,
    )
    try:
        blocks = await _preview_blocks(workspace, upstream, rel, session_id=sid)
        assert blocks
        node_ref = str(blocks[0]["node_ref"])
        assert len(node_ref) >= 32

        edit = UniversalFileEditCommand()
        with upstream_context(workspace=workspace, upstream=upstream):
            result = await edit.execute(
                **edit.validate_params(
                    {
                        "project_id": _PROJECT_UUID,
                        "session_id": sid,
                        "file_path": rel,
                        "operations": [
                            {
                                "type": "replace",
                                "node_ref": node_ref,
                                "value": replacement,
                            }
                        ],
                    }
                )
            )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)
        diff = await _preview_diff(workspace, upstream, sid, rel)
        assert diff_marker in diff
    finally:
        release_session(sid, rel)
