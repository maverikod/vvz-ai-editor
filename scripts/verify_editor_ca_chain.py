#!/usr/bin/env python3
"""Real-server acceptance pipeline for AI Editor -> Code Analysis.

The pipeline uses direct JSON-RPC against deployed CA and Editor servers. It
creates isolated CA projects/files through server commands only; it does not read
or write project files directly on disk.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient  # noqa: E402

DEFAULT_CA_HOST = "192.168.254.26"
DEFAULT_CA_PORT = 15010
DEFAULT_EDITOR_HOST = "192.168.254.26"
DEFAULT_EDITOR_PORT = 15000


class PipelineFailure(RuntimeError):
    """Failure with structured live-server evidence."""

    def __init__(self, message: str, evidence: Any = None) -> None:
        super().__init__(message)
        self.evidence = evidence


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except TypeError:
        return repr(value)


def _client(host: str, port: int, mtls_dir: Path) -> JsonRpcClient:
    cert = mtls_dir / "client" / "ai-editor.crt"
    key = mtls_dir / "client" / "ai-editor.key"
    ca = mtls_dir / "ca" / "ca.crt"
    return JsonRpcClient(
        host=host,
        port=port,
        protocol="https",
        cert=str(cert),
        key=str(key),
        ca=str(ca),
        check_hostname=False,
        timeout=120.0,
    )


def _unwrap(resp: Any) -> dict[str, Any]:
    if not isinstance(resp, dict):
        raise PipelineFailure("JSON-RPC response is not an object", resp)
    if resp.get("success") is False:
        raise PipelineFailure("JSON-RPC command failed", resp)
    data = resp.get("data")
    if isinstance(data, dict):
        if data.get("success") is False:
            raise PipelineFailure("JSON-RPC data payload failed", resp)
        return data
    return resp


async def _call(
    client: JsonRpcClient, command: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _unwrap(await client.execute_command(command, params or {}))


def _find_nested_str(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            found = value.get(key)
            if isinstance(found, str) and found.strip():
                return found.strip()
        for nested in value.values():
            found = _find_nested_str(nested, keys)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_nested_str(nested, keys)
            if found:
                return found
    return None


def _find_command_schema(help_payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        help_payload.get("schema"),
        help_payload.get("parameters"),
        (help_payload.get("data") or {}).get("schema")
        if isinstance(help_payload.get("data"), dict)
        else None,
        (help_payload.get("data") or {}).get("parameters")
        if isinstance(help_payload.get("data"), dict)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    raise PipelineFailure("help returned no command schema", help_payload)


async def _assert_universal_file_edit_same_process_metadata(
    ed: JsonRpcClient,
) -> dict[str, Any]:
    help_payload = await ed.help("universal_file_edit")
    if not isinstance(help_payload, dict) or help_payload.get("success") is False:
        raise PipelineFailure("help(universal_file_edit) failed", help_payload)
    schema = _find_command_schema(help_payload)
    use_queue = schema.get("x-use-queue")
    if use_queue is not False:
        raise PipelineFailure(
            "universal_file_edit schema.x-use-queue is not false",
            {"x-use-queue": use_queue, "help": help_payload},
        )
    return {"command": "universal_file_edit", "schema_x_use_queue": use_queue}


async def _edit(ed: JsonRpcClient, params: dict[str, Any]) -> dict[str, Any]:
    edit_response = await _call(ed, "universal_file_edit", params)
    job_id = _find_nested_str(edit_response, {"job_id", "queue_job_id"})
    if job_id:
        raise PipelineFailure(
            "universal_file_edit returned a queued job envelope",
            {"job_id": job_id, "response": edit_response},
        )
    return {"mode": "sync", "response": edit_response}


def _candidate_lists(payload: Any) -> list[list[Any]]:
    lists: list[list[Any]] = []
    if isinstance(payload, list):
        lists.append(payload)
    if isinstance(payload, dict):
        for key in ("watch_dirs", "directories", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                lists.append(value)
            elif isinstance(value, dict):
                lists.extend(_candidate_lists(value))
    return lists


async def _discover_watch_dir_id(ca: JsonRpcClient) -> dict[str, Any]:
    payload = await _call(ca, "list_watch_dirs", {})
    for entries in _candidate_lists(payload):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            deleted = bool(
                entry.get("deleted")
                or entry.get("is_deleted")
                or str(entry.get("status") or "").lower() == "deleted"
            )
            watch_dir_id = (
                entry.get("watch_dir_id") or entry.get("id") or entry.get("uuid")
            )
            if not deleted and isinstance(watch_dir_id, str) and watch_dir_id:
                return {"watch_dir_id": watch_dir_id, "source": "list_watch_dirs"}
    raise PipelineFailure(
        "CA list_watch_dirs returned no non-deleted watch dirs", payload
    )


async def _create_project(
    ca: JsonRpcClient, watch_dir_id: str, scenario_slug: str
) -> dict[str, str]:
    project_name = f"verify_editor_{scenario_slug}_{uuid.uuid4().hex[:8]}"
    project = await _call(
        ca,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": project_name,
            "description": f"verify_editor_ca_chain {scenario_slug}",
            "create_venv": False,
            "apply_template": False,
        },
    )
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise PipelineFailure("create_project returned no project_id", project)
    return {"project_id": project_id, "project_name": project_name}


async def _create_session(ca: JsonRpcClient, scenario_slug: str) -> str:
    session = await _call(
        ca, "session_create", {"comment": f"verify_editor_ca_chain {scenario_slug}"}
    )
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise PipelineFailure("session_create returned no session_id", session)
    return session_id


async def _close_suppress(
    ed: JsonRpcClient, project_id: str, session_id: str, file_path: str
) -> dict[str, Any] | None:
    try:
        return await _call(
            ed,
            "universal_file_close",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return {"close_error": repr(exc)}


async def _read_file_text(
    ca: JsonRpcClient, project_id: str, file_path: str, *, end_line: int | None = None
) -> str:
    params: dict[str, Any] = {
        "project_id": project_id,
        "file_path": file_path,
        "start_line": 1,
        "allow_healthy_line_ops": True,
    }
    if end_line is not None:
        params["end_line"] = end_line
    lines_payload = await _call(
        ca,
        "get_file_lines",
        params,
    )
    raw_lines = lines_payload.get("lines")
    if isinstance(raw_lines, list):
        lines: list[str] = []
        for row in raw_lines:
            if isinstance(row, str):
                lines.append(row)
            elif isinstance(row, dict):
                text = row.get("content") or row.get("text") or row.get("line")
                if isinstance(text, str):
                    lines.append(text)
        return "\n".join(lines)
    content = lines_payload.get("content") or lines_payload.get("text")
    if isinstance(content, str):
        return content
    raise PipelineFailure("get_file_lines returned no readable content", lines_payload)


async def _open_edit_write_read(
    *,
    ca: JsonRpcClient,
    ed: JsonRpcClient,
    watch_dir_id: str,
    scenario_slug: str,
    file_path: str,
    initial_content: str,
    operations: list[dict[str, Any]],
    expected_substrings: list[str],
    verify_after_upload: bool = False,
    format_python: bool = False,
    read_end_line: int | None = None,
) -> dict[str, Any]:
    project = await _create_project(ca, watch_dir_id, scenario_slug)
    project_id = project["project_id"]
    session_id = await _create_session(ca, scenario_slug)
    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "create": True,
            "initial_content": initial_content,
        },
    )
    close_result: dict[str, Any] | None = None
    try:
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": operations,
            }
        )
        write_common: dict[str, Any] = {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
        }
        if format_python:
            write_common["format_python"] = True
        preview = await _call(
            ed,
            "universal_file_write",
            {**write_common, "write_mode": "preview"},
        )
        preview_text = json.dumps(preview, ensure_ascii=False)
        missing_preview = [
            expected for expected in expected_substrings if expected not in preview_text
        ]
        if missing_preview:
            raise PipelineFailure(
                "preview did not contain edited draft content",
                {"missing": missing_preview, "preview": preview},
            )
        commit_params = {**write_common, "write_mode": "commit"}
        if verify_after_upload:
            commit_params["verify_after_upload"] = True
        commit = await _call(ed, "universal_file_write", commit_params)
        if not commit.get("uploaded"):
            raise PipelineFailure("commit did not upload changes", commit)
        if verify_after_upload:
            ca_verify = commit.get("ca_verify") or {}
            if isinstance(ca_verify, dict) and not ca_verify.get("verified"):
                raise PipelineFailure("commit ca_verify failed", commit)
        content = await _read_file_text(
            ca, project_id, file_path, end_line=read_end_line
        )
        missing_content = [
            expected for expected in expected_substrings if expected not in content
        ]
        if missing_content:
            raise PipelineFailure(
                "CA readback did not contain expected content",
                {"missing": missing_content, "content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "edit": _jsonable(edit),
            "preview_has_changes": preview.get("has_changes"),
            "commit_uploaded": commit.get("uploaded"),
            "ca_verify": commit.get("ca_verify"),
            "readback_excerpt": content[:1000],
        }
    finally:
        close_result = await _close_suppress(ed, project_id, session_id, file_path)
        if close_result:
            _ = close_result


async def _scenario_edit_preview_text(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    return await _open_edit_write_read(
        ca=ca,
        ed=ed,
        watch_dir_id=watch_dir_id,
        scenario_slug="296e02c9",
        file_path="verify/edit_lifecycle.txt",
        initial_content="verify chain initial\nsecond line\n",
        operations=[
            {
                "type": "replace",
                "start_line": 1,
                "end_line": 1,
                "content": "verify chain COMMITTED\n",
            }
        ],
        expected_substrings=["verify chain COMMITTED"],
        read_end_line=2,
    )


async def _scenario_yaml_root_insert(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for label, parent_pointer in (("empty", ""), ("slash", "/")):
        details[label] = await _open_edit_write_read(
            ca=ca,
            ed=ed,
            watch_dir_id=watch_dir_id,
            scenario_slug=f"690f768c_{label}",
            file_path=f"verify/yaml_root_{label}.yaml",
            initial_content="first: 1\nthird: 3\n",
            operations=[
                {
                    "type": "insert",
                    "parent_json_pointer": parent_pointer,
                    "key": "second",
                    "value": 2,
                }
            ],
            expected_substrings=["second"],
            read_end_line=3,
        )
    return details


def _find_preview_node_ref(value: Any, needles: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        serialized = json.dumps(value, ensure_ascii=False)
        node_text = value.get("text")
        attributes = value.get("attributes")
        is_class_node = str(value.get("type") or "").lower() == "class" or (
            isinstance(attributes, dict) and attributes.get("node_type") == "ClassDef"
        )
        text_has_needles = isinstance(node_text, str) and all(
            needle in node_text for needle in needles
        )
        is_direct_match = all(needle in serialized for needle in needles) and (
            is_class_node or text_has_needles
        )
        if is_direct_match:
            for key in ("node_ref", "short_id", "stable_id"):
                found = value.get(key)
                if isinstance(found, (str, int)) and str(found):
                    return str(found)
        for nested in value.values():
            found = _find_preview_node_ref(nested, needles)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_preview_node_ref(nested, needles)
            if found:
                return found
    return None


async def _scenario_python_header_comment(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    project = await _create_project(ca, watch_dir_id, "86288c9c")
    project_id = project["project_id"]
    session_id = await _create_session(ca, "86288c9c")
    file_path = "verify/header_comment.py"
    initial_content = (
        '"""Live verifier fixture for class header edits."""\n'
        "\n"
        "class Foo:  # type: ignore[misc]\n"
        '    """Fixture class with a required docstring."""\n'
        "\n"
        "    def existing(self) -> int:\n"
        '        """Return the existing fixture value.\n'
        "\n"
        "        Returns:\n"
        "            Existing fixture value.\n"
        '        """\n'
        "        return 1\n"
    )
    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "create": True,
            "initial_content": initial_content,
        },
    )
    try:
        preview = await _call(
            ed,
            "universal_file_preview",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
            },
        )
        class_ref = _find_preview_node_ref(preview, ("class Foo",))
        if not class_ref:
            raise PipelineFailure("preview did not expose class Foo node_ref", preview)
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "insert",
                        "parent_node_id": class_ref,
                        "position": "last",
                        "code_lines": [
                            "",
                            "def added(self) -> int:",
                            '    """Return the inserted fixture value.',
                            "",
                            "    Returns:",
                            "        Inserted fixture value.",
                            '    """',
                            "    return 2",
                        ],
                    }
                ],
            },
        )
        commit = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "commit",
                "format_python": True,
            },
        )
        if not commit.get("uploaded"):
            raise PipelineFailure("python commit did not upload changes", commit)
        content = await _read_file_text(ca, project_id, file_path, end_line=18)
        class_header = next(
            (line for line in content.splitlines() if line.startswith("class Foo")),
            "",
        )
        if "# type: ignore[misc]" not in class_header:
            raise PipelineFailure(
                "Python class header trailing comment was not preserved",
                {"class_header": class_header, "content": content},
            )
        if "def added" not in content:
            raise PipelineFailure(
                "Python inserted method missing from CA readback", content
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "class_node_ref": class_ref,
            "edit": _jsonable(edit),
            "commit_uploaded": commit.get("uploaded"),
            "class_header": class_header,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


def _find_class_block_node_ref(preview: dict[str, Any], needle: str) -> str | None:
    """Return the node_ref of the preview BLOCK typed 'class' containing *needle*.

    ``_find_preview_node_ref`` walks the whole payload and can match the focus
    node, whose text spans the entire file — resolving 'class Foo' to the first
    statement's ref (observed live: the module docstring, bug bdce5d39 evidence
    2/3 turned out to be exactly this scenario-side mis-resolution). Restricting
    the search to typed blocks pins the ref to the class itself.

    Args:
        preview: universal_file_preview payload.
        needle: Substring that must appear in the class block's text.

    Returns:
        The class block's node reference, or None when absent.
    """
    blocks = preview.get("blocks")
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if not isinstance(block, dict):
            continue
        summary = block.get("summary") or {}
        block_type = str(summary.get("type") or block.get("type") or "").lower()
        text = block.get("text")
        if block_type == "class" and isinstance(text, str) and needle in text:
            for key in ("node_ref", "short_id", "stable_id"):
                found = block.get(key)
                if isinstance(found, (str, int)) and str(found):
                    return str(found)
    return None


def _find_smallest_preview_node_ref(value: Any, needle: str) -> str | None:
    """Return the node_ref of the SMALLEST preview node whose text has *needle*.

    ``_find_preview_node_ref`` returns the first structural match, which for a
    module-level needle can resolve to an enclosing block instead of the exact
    statement; deleting by such a ref removes the wrong node (observed live:
    the module docstring). Choosing the candidate with the shortest ``text``
    pins the ref to the single statement that carries the needle.

    Args:
        value: Preview payload subtree (dict/list/scalar).
        needle: Substring that must appear in the node's own ``text``.

    Returns:
        The best node reference, or None when no node text contains needle.
    """
    best: tuple[int, str] | None = None

    def _walk(node: Any) -> None:
        nonlocal best
        if isinstance(node, dict):
            node_text = node.get("text")
            if isinstance(node_text, str) and needle in node_text:
                for key in ("node_ref", "short_id", "stable_id"):
                    found = node.get(key)
                    if isinstance(found, (str, int)) and str(found):
                        candidate = (len(node_text), str(found))
                        if best is None or candidate[0] < best[0]:
                            best = candidate
                        break
            for nested in node.values():
                _walk(nested)
        elif isinstance(node, list):
            for nested in node:
                _walk(nested)

    _walk(value)
    return best[1] if best else None


async def _scenario_sibling_insert_delete_trivia(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Live regression for bug ed579e33 (residual of 86288c9c).

    Also live-verifies bug bdce5d39: the inserted sibling CARRIES a real
    trailing comment (previously unaddressable in preview), is inserted with
    ``position="before"`` relative to the class, must land BETWEEN the module
    docstring and the class (not above the docstring), must be addressable in
    re-preview, and deleting it by its own node_ref must remove exactly that
    statement. Inserting/deleting the sibling must leave the inline-comment
    trivia of the untouched class/def headers byte-identical (bug ed579e33).

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments (hosts, ports, mtls paths).
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with per-phase header lines and commit flags.
    """
    project = await _create_project(ca, watch_dir_id, "ed579e33")
    project_id = project["project_id"]
    session_id = await _create_session(ca, "ed579e33")
    file_path = "verify/sibling_trivia.py"
    class_header_expected = "class Foo:  # type: ignore[misc]"
    bar_header_expected = "    def bar(self) -> None:  # note"
    initial_content = (
        '"""Live verifier fixture for sibling insert/delete trivia (ed579e33)."""\n'
        "\n"
        "class Foo:  # type: ignore[misc]\n"
        '    """Fixture class with a required docstring."""\n'
        "\n"
        "    def bar(self) -> None:  # note\n"
        '        """Do nothing.\n'
        "\n"
        "        Returns:\n"
        "            None.\n"
        '        """\n'
        "        return None\n"
    )

    def _header_lines(content: str) -> tuple[str, str]:
        class_line = next(
            (line for line in content.splitlines() if line.startswith("class Foo")),
            "",
        )
        bar_line = next(
            (
                line
                for line in content.splitlines()
                if line.strip().startswith("def bar")
            ),
            "",
        )
        return class_line, bar_line

    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "create": True,
            "initial_content": initial_content,
        },
    )
    try:
        preview = await _call(
            ed,
            "universal_file_preview",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
            },
        )
        class_ref = _find_class_block_node_ref(preview, "class Foo")
        if not class_ref:
            raise PipelineFailure("preview did not expose class Foo node_ref", preview)
        insert_edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "insert",
                        "target_node_id": class_ref,
                        "position": "before",
                        "code_lines": ["X = 1  # doc: ed579e33 sibling fixture"],
                    }
                ],
            },
        )
        insert_commit = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "commit",
                "format_python": True,
            },
        )
        if not insert_commit.get("uploaded"):
            raise PipelineFailure(
                "sibling insert commit did not upload changes", insert_commit
            )
        after_insert = await _read_file_text(ca, project_id, file_path, end_line=12)
        insert_class_header, insert_bar_header = _header_lines(after_insert)
        insert_lines = after_insert.splitlines()
        sibling_idx = next(
            (i for i, line in enumerate(insert_lines) if line.startswith("X = 1")),
            None,
        )
        docstring_idx = next(
            (
                i
                for i, line in enumerate(insert_lines)
                if "Live verifier fixture" in line
            ),
            None,
        )
        class_idx = next(
            (i for i, line in enumerate(insert_lines) if line.startswith("class Foo")),
            None,
        )
        if sibling_idx is None:
            raise PipelineFailure(
                "inserted sibling statement missing from CA readback", after_insert
            )
        if docstring_idx is None or class_idx is None:
            raise PipelineFailure(
                "fixture landmarks missing from CA readback", after_insert
            )
        if not docstring_idx < sibling_idx < class_idx:
            raise PipelineFailure(
                "sibling insert misplaced relative to docstring/class (bdce5d39)",
                {
                    "docstring_idx": docstring_idx,
                    "sibling_idx": sibling_idx,
                    "class_idx": class_idx,
                    "content": after_insert,
                },
            )
        if insert_class_header != class_header_expected:
            raise PipelineFailure(
                "class header trivia corrupted by sibling insert (repro A)",
                {"class_header": insert_class_header, "content": after_insert},
            )
        if insert_bar_header != bar_header_expected:
            raise PipelineFailure(
                "method header trivia corrupted by sibling insert (repro A)",
                {"bar_header": insert_bar_header, "content": after_insert},
            )
        re_preview = await _call(
            ed,
            "universal_file_preview",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
            },
        )
        sibling_ref = _find_smallest_preview_node_ref(re_preview, "X = 1")
        if not sibling_ref:
            raise PipelineFailure(
                "re-preview did not expose inserted sibling node_ref", re_preview
            )
        delete_edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "delete",
                        "node_id": sibling_ref,
                    }
                ],
            },
        )
        delete_commit = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "commit",
                "format_python": True,
            },
        )
        if not delete_commit.get("uploaded"):
            raise PipelineFailure(
                "sibling delete commit did not upload changes", delete_commit
            )
        after_delete = await _read_file_text(ca, project_id, file_path, end_line=12)
        delete_class_header, delete_bar_header = _header_lines(after_delete)
        if "Live verifier fixture" not in after_delete:
            raise PipelineFailure(
                "module docstring lost after sibling delete", after_delete
            )
        if "X = 1" in after_delete:
            raise PipelineFailure(
                "deleted sibling statement still present in CA readback", after_delete
            )
        if delete_class_header != class_header_expected:
            raise PipelineFailure(
                "class header trivia stripped by sibling delete (repro B)",
                {"class_header": delete_class_header, "content": after_delete},
            )
        if delete_bar_header != bar_header_expected:
            raise PipelineFailure(
                "method header trivia stripped by sibling delete (repro B)",
                {"bar_header": delete_bar_header, "content": after_delete},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "insert_edit": _jsonable(insert_edit),
            "delete_edit": _jsonable(delete_edit),
            "insert_commit_uploaded": insert_commit.get("uploaded"),
            "delete_commit_uploaded": delete_commit.get("uploaded"),
            "class_header_after_insert": insert_class_header,
            "class_header_after_delete": delete_class_header,
            "bar_header_after_insert": insert_bar_header,
            "bar_header_after_delete": delete_bar_header,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


async def _scenario_sibling_import(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    project = await _create_project(ca, watch_dir_id, "bf98dd98")
    project_id = project["project_id"]
    module_session_id = await _create_session(ca, "bf98dd98_module")
    module_path = "verify/sibling_mod.py"
    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": module_session_id,
            "file_path": module_path,
            "create": True,
            "initial_content": (
                '"""Live verifier sibling module fixture."""\n'
                "\n"
                "VALUE = 42\n"
            ),
        },
    )
    try:
        module_edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": module_session_id,
                "file_path": module_path,
                "operations": [
                    {
                        "type": "insert",
                        "parent_node_id": "__root__",
                        "position": "last",
                        "code_lines": [
                            "",
                            "EXTRA = VALUE",
                        ],
                    }
                ],
            },
        )
        module_commit = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": module_session_id,
                "file_path": module_path,
                "write_mode": "commit",
            },
        )
        if not module_commit.get("uploaded"):
            raise PipelineFailure("sibling module commit did not upload", module_commit)
    finally:
        await _close_suppress(ed, project_id, module_session_id, module_path)

    importer_session_id = await _create_session(ca, "bf98dd98_importer")
    importer_path = "verify/importer.py"
    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": importer_session_id,
            "file_path": importer_path,
            "create": True,
            "initial_content": (
                '"""Live verifier importer fixture."""\n'
                "\n"
                "from sibling_mod import VALUE\n"
                "\n"
                "RESULT = VALUE\n"
            ),
        },
    )
    try:
        importer_edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": importer_session_id,
                "file_path": importer_path,
                "operations": [
                    {
                        "type": "insert",
                        "parent_node_id": "__root__",
                        "position": "last",
                        "code_lines": [
                            "",
                            "def get_value() -> int:",
                            '    """Return the imported fixture value.',
                            "",
                            "    Returns:",
                            "        Imported fixture value.",
                            '    """',
                            "    return VALUE",
                        ],
                    }
                ],
            },
        )
        commit_params: dict[str, Any] = {
            "project_id": project_id,
            "session_id": importer_session_id,
            "file_path": importer_path,
            "write_mode": "commit",
            "format_python": True,
            "verify_after_upload": True,
        }
        importer_commit = await _call(ed, "universal_file_write", commit_params)
        if not importer_commit.get("uploaded"):
            raise PipelineFailure("importer commit did not upload", importer_commit)
        ca_verify = importer_commit.get("ca_verify") or {}
        if isinstance(ca_verify, dict) and not ca_verify.get("verified"):
            raise PipelineFailure(
                "importer verify_after_upload failed", importer_commit
            )
        content = await _read_file_text(ca, project_id, importer_path, end_line=12)
        if "from sibling_mod import VALUE" not in content:
            raise PipelineFailure("import line missing from CA readback", content)
        return {
            **project,
            "module": {
                "file_path": module_path,
                "edit": _jsonable(module_edit),
                "commit_uploaded": module_commit.get("uploaded"),
            },
            "importer": {
                "session_id": importer_session_id,
                "file_path": importer_path,
                "edit": _jsonable(importer_edit),
                "commit_uploaded": importer_commit.get("uploaded"),
                "ca_verify": importer_commit.get("ca_verify"),
                "readback_excerpt": content[:1000],
            },
        }
    finally:
        await _close_suppress(ed, project_id, importer_session_id, importer_path)


async def _scenario_ini_toml(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    ini = await _open_edit_write_read(
        ca=ca,
        ed=ed,
        watch_dir_id=watch_dir_id,
        scenario_slug="ini_support",
        file_path="verify/settings.ini",
        initial_content="first = 1\nlast = 3\n[server]\nhost: localhost\n",
        operations=[
            {
                "type": "insert",
                "parent_json_pointer": "",
                "key": "middle",
                "value": "2",
                "after_key": "first",
            }
        ],
        expected_substrings=["middle"],
        read_end_line=5,
    )
    toml = await _open_edit_write_read(
        ca=ca,
        ed=ed,
        watch_dir_id=watch_dir_id,
        scenario_slug="toml_support",
        file_path="verify/settings.toml",
        initial_content='first = 1\nlast = 3\n[server]\nhost = "localhost"\n',
        operations=[
            {
                "type": "insert",
                "parent_json_pointer": "",
                "key": "middle",
                "value": 2,
                "after_key": "first",
            }
        ],
        expected_substrings=["middle"],
        read_end_line=5,
    )
    return {"ini": ini, "toml": toml}


async def _run_scenario(
    name: str,
    fn: Callable[
        [JsonRpcClient, JsonRpcClient, argparse.Namespace, str],
        Awaitable[dict[str, Any]],
    ],
    ca: JsonRpcClient,
    ed: JsonRpcClient,
    args: argparse.Namespace,
    watch_dir_id: str,
) -> dict[str, Any]:
    try:
        details = await fn(ca, ed, args, watch_dir_id)
        return {"name": name, "status": "passed", "details": _jsonable(details)}
    except PipelineFailure as exc:
        return {
            "name": name,
            "status": "failed",
            "error": str(exc),
            "details": _jsonable(exc.evidence),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "status": "failed",
            "error": repr(exc),
            "details": traceback.format_exc(),
        }


async def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    ca = _client(args.ca_host, args.ca_port, args.mtls_dir)
    ed = _client(args.editor_host, args.editor_port, args.mtls_dir)

    watch_dir_source = "override"
    watch_dir_id = args.watch_dir_id
    if not watch_dir_id:
        discovered = await _discover_watch_dir_id(ca)
        watch_dir_id = discovered["watch_dir_id"]
        watch_dir_source = discovered["source"]

    scenarios: list[dict[str, Any]] = []
    metadata = await _run_scenario(
        "universal_file_edit_metadata",
        lambda _ca, _ed, _args, _watch_dir_id: (
            _assert_universal_file_edit_same_process_metadata(_ed)
        ),
        ca,
        ed,
        args,
        watch_dir_id,
    )
    scenarios.append(metadata)

    scenario_fns: list[
        tuple[
            str,
            Callable[
                [JsonRpcClient, JsonRpcClient, argparse.Namespace, str],
                Awaitable[dict[str, Any]],
            ],
        ]
    ] = [
        ("296e02c9_edit_preview_commit_readback", _scenario_edit_preview_text),
        ("690f768c_yaml_root_key_parent_empty_and_slash", _scenario_yaml_root_insert),
        (
            "86288c9c_python_header_comment_preservation",
            _scenario_python_header_comment,
        ),
        (
            "ed579e33_sibling_insert_delete_header_trivia",
            _scenario_sibling_insert_delete_trivia,
        ),
        ("bf98dd98_sibling_import_no_false_import_not_found", _scenario_sibling_import),
        ("ini_toml_structured_edit_commit_readback", _scenario_ini_toml),
    ]
    for name, fn in scenario_fns:
        scenarios.append(await _run_scenario(name, fn, ca, ed, args, watch_dir_id))

    failed = [scenario for scenario in scenarios if scenario["status"] != "passed"]
    return {
        "pipeline": "verify_editor_ca_chain",
        "transport": "direct_jsonrpc",
        "servers": {
            "ca": {"host": args.ca_host, "port": args.ca_port},
            "editor": {"host": args.editor_host, "port": args.editor_port},
        },
        "watch_dir": {"id": watch_dir_id, "source": watch_dir_source},
        "summary": {
            "passed": len(scenarios) - len(failed),
            "failed": len(failed),
            "total": len(scenarios),
        },
        "scenarios": scenarios,
        "coverage_notes": {
            "bef15b14": (
                "Not live-forced non-invasively: this pipeline does not mutate "
                "CAS/QueueManager/mcp_proxy_adapter configuration to fake a "
                "queued upstream sync-cap response. Full same-process edit "
                "and editor-to-CA commit flows are covered live."
            )
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-server AI Editor -> CA acceptance pipeline"
    )
    parser.add_argument(
        "--watch-dir-id",
        default=_env("AI_EDITOR_WATCH_DIR_ID", ""),
        help=(
            "CA watch_dir_id to use. Defaults to AI_EDITOR_WATCH_DIR_ID; "
            "when unset, auto-discovers first non-deleted CA list_watch_dirs id."
        ),
    )
    parser.add_argument("--ca-host", default=_env("AI_EDITOR_CA_HOST", DEFAULT_CA_HOST))
    parser.add_argument(
        "--ca-port",
        type=int,
        default=int(_env("AI_EDITOR_CA_PORT", str(DEFAULT_CA_PORT))),
    )
    parser.add_argument(
        "--editor-host", default=_env("AI_EDITOR_HOST", DEFAULT_EDITOR_HOST)
    )
    parser.add_argument(
        "--editor-port",
        type=int,
        default=int(_env("AI_EDITOR_PORT", str(DEFAULT_EDITOR_PORT))),
    )
    parser.add_argument(
        "--mtls-dir",
        type=Path,
        default=Path(
            _env(
                "AI_EDITOR_MTLS_DIR",
                str(REPO_ROOT / "mtls_certificates/mtls_certificates"),
            )
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = asyncio.run(run_pipeline(args))
    except PipelineFailure as exc:
        result = {
            "pipeline": "verify_editor_ca_chain",
            "summary": {"passed": 0, "failed": 1, "total": 1},
            "scenarios": [
                {
                    "name": "pipeline_setup",
                    "status": "failed",
                    "error": str(exc),
                    "details": _jsonable(exc.evidence),
                }
            ],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if int(result["summary"]["failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
