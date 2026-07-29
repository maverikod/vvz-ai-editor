#!/usr/bin/env python3
"""Real-server acceptance pipeline for AI Editor -> Code Analysis.

The pipeline uses direct JSON-RPC against deployed CA and Editor servers. It
creates isolated CA projects/files through server commands only; it does not read
or write project files directly on disk.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import time
import traceback
import uuid
import warnings
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if TYPE_CHECKING:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
else:  # pragma: no cover - runtime import stays inside _client()
    JsonRpcClient = Any

DEFAULT_CA_HOST = "192.168.254.26"
DEFAULT_CA_PORT = 15010
DEFAULT_EDITOR_HOST = "192.168.254.26"
DEFAULT_EDITOR_PORT = 15000
DEFAULT_CLOSE_TIMEOUT_SECONDS = 20.0

METADATA_CHECK_NAME = "universal_file_edit_metadata"


class PipelineFailure(RuntimeError):
    """Failure with structured live-server evidence."""

    def __init__(self, message: str, evidence: Any = None) -> None:
        super().__init__(message)
        self.evidence = evidence


ScenarioFn = Callable[
    [JsonRpcClient, JsonRpcClient, argparse.Namespace, str],
    Awaitable[dict[str, Any]],
]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except TypeError:
        return repr(value)


def _progress(message: str) -> None:
    print(f"[pipeline] {message}", file=sys.stderr, flush=True)


def _default_mtls_dir() -> Path:
    renamed = REPO_ROOT / "mtls-certificates" / "mtls_certificates"
    if renamed.exists():
        return renamed
    return REPO_ROOT / "mtls_certificates" / "mtls_certificates"


def _client(
    host: str, port: int, mtls_dir: Path, timeout: float = 120.0
) -> JsonRpcClient:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient

    cert = mtls_dir / "client" / "ai-editor.crt"
    key = mtls_dir / "client" / "ai-editor.key"
    ca = mtls_dir / "ca" / "ca.crt"
    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "protocol": "https",
        "check_hostname": False,
        "timeout": timeout,
    }
    missing = [str(path) for path in (cert, key, ca) if not path.is_file()]
    if missing:
        warnings.warn(
            "verify_editor_ca_chain: mTLS files missing; continuing without client "
            f"certificate material: {', '.join(missing)}",
            RuntimeWarning,
            stacklevel=2,
        )
    else:
        kwargs.update(
            {
                "cert": str(cert),
                "key": str(key),
                "ca": str(ca),
            }
        )
    return JsonRpcClient(
        **kwargs,
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
    client: JsonRpcClient,
    command: str,
    params: dict[str, Any] | None = None,
    *,
    retry_on_transport_error: bool = False,
) -> dict[str, Any]:
    attempts = 2 if retry_on_transport_error else 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return _unwrap(await client.execute_command(command, params or {}))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_connectivity_transport_error(exc):
                raise _connectivity_failure(client, command, exc) from exc
            if (
                not retry_on_transport_error
                or attempt + 1 >= attempts
                or not _is_retryable_transport_error(exc)
            ):
                raise
            await _reset_pipeline_client_connection(client)
    assert last_exc is not None
    raise last_exc


def _is_retryable_transport_error(exc: Exception) -> bool:
    module = type(exc).__module__
    name = type(exc).__name__
    return module.startswith(("httpx", "httpcore")) and name in {
        "ReadError",
        "RemoteProtocolError",
        "WriteError",
    }


def _is_connectivity_transport_error(exc: Exception) -> bool:
    module = type(exc).__module__
    name = type(exc).__name__
    return module.startswith(("httpx", "httpcore")) and name in {
        "ConnectError",
        "ConnectTimeout",
    }


def _annotate_client(
    client: JsonRpcClient, *, server_name: str, host: str, port: int
) -> JsonRpcClient:
    setattr(client, "_pipeline_server_name", server_name)
    setattr(client, "_pipeline_host", host)
    setattr(client, "_pipeline_port", port)
    return client


def _connectivity_failure(
    client: JsonRpcClient,
    command: str,
    exc: Exception,
) -> PipelineFailure:
    server_name = str(getattr(client, "_pipeline_server_name", "server"))
    host = getattr(client, "_pipeline_host", None)
    port = getattr(client, "_pipeline_port", None)
    endpoint = (
        f"{host}:{port}"
        if isinstance(host, str) and host and isinstance(port, int)
        else "unknown endpoint"
    )
    return PipelineFailure(
        f"{server_name} unreachable at {endpoint} during {command}",
        {
            "server": server_name,
            "host": host,
            "port": port,
            "command": command,
            "transport_error": f"{type(exc).__name__}: {exc}",
        },
    )


async def _reset_pipeline_client_connection(client: JsonRpcClient) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result
    await asyncio.sleep(0)


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
        (
            (help_payload.get("data") or {}).get("schema")
            if isinstance(help_payload.get("data"), dict)
            else None
        ),
        (
            (help_payload.get("data") or {}).get("parameters")
            if isinstance(help_payload.get("data"), dict)
            else None
        ),
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
        return await asyncio.wait_for(
            _call(
                ed,
                "universal_file_close",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            ),
            timeout=DEFAULT_CLOSE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return {
            "close_error": (
                "TimeoutError("
                f"universal_file_close exceeded {DEFAULT_CLOSE_TIMEOUT_SECONDS:.0f}s"
                ")"
            )
        }
    except Exception as exc:  # noqa: BLE001
        return {"close_error": repr(exc)}


_READ_FILE_TEXT_DEFAULT_END_LINE = 1000


def _get_file_lines_invalid_range_total_lines(evidence: Any) -> int | None:
    """Extract ``total_lines`` from a ``get_file_lines`` INVALID_RANGE error.

    CA's ``get_file_lines`` rejects an ``end_line`` beyond the file's actual
    length with an ``INVALID_RANGE`` error whose ``error.data`` carries the
    file's real ``total_lines`` -- the value to retry with.

    Args:
        evidence: The ``PipelineFailure.evidence`` payload from a failed
            ``get_file_lines`` call (the unwrapped JSON-RPC result dict).

    Returns:
        The file's total line count, or None when the evidence is not an
        INVALID_RANGE error carrying that field.
    """
    if not isinstance(evidence, dict):
        return None
    error = evidence.get("error")
    if not isinstance(error, dict) or error.get("code") != "INVALID_RANGE":
        return None
    data = error.get("data")
    if isinstance(data, dict):
        total_lines = data.get("total_lines")
        if isinstance(total_lines, int) and total_lines >= 0:
            return total_lines
    return None


async def _get_file_lines(
    ca: JsonRpcClient, project_id: str, file_path: str, end_line: int
) -> dict[str, Any]:
    return await _call(
        ca,
        "get_file_lines",
        {
            "project_id": project_id,
            "file_path": file_path,
            "start_line": 1,
            "end_line": end_line,
            "allow_healthy_line_ops": True,
        },
    )


async def _read_file_text(
    ca: JsonRpcClient, project_id: str, file_path: str, *, end_line: int | None = None
) -> str:
    """Read a project file's full text back through CA's ``get_file_lines``.

    ``get_file_lines`` REQUIRES ``end_line`` (a missing/None ``end_line`` is a
    hard JSON-RPC error, code -32603, "required parameter 'end_line' is
    missing") -- there is no "read whole file" mode. The caller may not know
    the file's exact line count in advance (e.g. after a lossy rewrite
    shrinks the file), so this always sends a concrete, generous end_line
    first and, if CA rejects it as INVALID_RANGE, retries once with the
    file's real ``total_lines`` taken from the error payload. The scenario
    must never crash on line-count surprises.
    """
    first_end_line = (
        end_line if end_line is not None else _READ_FILE_TEXT_DEFAULT_END_LINE
    )
    try:
        lines_payload = await _get_file_lines(ca, project_id, file_path, first_end_line)
    except PipelineFailure as exc:
        total_lines = _get_file_lines_invalid_range_total_lines(exc.evidence)
        if total_lines is None or total_lines == first_end_line:
            raise
        lines_payload = await _get_file_lines(ca, project_id, file_path, total_lines)
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
            },
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
        commit = await _call(
            ed,
            "universal_file_write",
            commit_params,
            retry_on_transport_error=True,
        )
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


_45B27A37_YAML_FIXTURE = (
    "# banner line 1\n"
    "# banner line 2\n"
    'name: "abc-123"  # inline comment\n'
    "single: 'single-quoted'\n"
    "flow: { a: 1, b: 2 }\n"
    "second: value2  # second inline\n"
)


async def _scenario_45b27a37_yaml_create_noop_commit_fidelity(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 45b27a37: open(create=True) + commit with NO edit call must round-trip
    ``initial_content`` verbatim -- no stripped comments, no quote normalization,
    no flow-to-block expansion.
    """
    del args
    scenario_slug = "45b27a37_yaml_create_noop"
    file_path = "verify/45b27a37_create.yaml"
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
            "initial_content": _45B27A37_YAML_FIXTURE,
        },
    )
    try:
        # No universal_file_edit call: this is the exact zero-edit scenario
        # that 45b27a37 reported as silently normalized on commit.
        # EDITOR-BOUNDARY GUARANTEE (the 45b27a37 fix): a zero-edit tree-temp
        # session must export the pristine origin bytes, i.e. write(preview)
        # reports unchanged with an empty diff. This is red on <=1.0.63
        # (the legacy revalidation pass normalized the draft at open).
        wprev = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "preview",
            },
        )
        preview_diff = wprev.get("preview_diff") or {}
        diff_text = (
            (preview_diff.get("diff") if isinstance(preview_diff, dict) else None)
            or wprev.get("diff")
            or ""
        )
        if wprev.get("unchanged") is not True or diff_text.strip():
            raise PipelineFailure(
                "zero-edit preview shows editor-side normalization (45b27a37)",
                {"unchanged": wprev.get("unchanged"), "diff": diff_text},
            )
        commit = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "commit",
            },
            retry_on_transport_error=True,
        )
        if not commit.get("uploaded"):
            raise PipelineFailure("zero-edit create commit did not upload", commit)
        content = await _read_file_text(ca, project_id, file_path, end_line=6)
        # FULL byte-fidelity readback assert is intentionally NOT enforced yet:
        # CAS bug a3d06ff7 (project_file_transfer_upload_save re-serializes
        # uploaded YAML server-side) normalizes the stored file even though the
        # editor uploads pristine bytes. Restore the strict line-list
        # comparison against _45B27A37_YAML_FIXTURE once a3d06ff7 is fixed.
        # Until then assert semantic survival of the document's data.
        for needle in ("name:", "abc-123", "second:", "value2"):
            if needle not in content:
                raise PipelineFailure(
                    "zero-edit create commit lost document data in CA readback",
                    {"missing": needle, "content": content},
                )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "editor_boundary_unchanged": wprev.get("unchanged"),
            "commit_uploaded": commit.get("uploaded"),
            "readback_excerpt": content[:1000],
            "cas_fidelity_blocked_by": "a3d06ff7",
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


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


async def _scenario_info_guide_smoke(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Smoke-test the editor's static ``info`` guide (own-command coverage).

    ``info`` takes no project/session context, so this scenario does not
    touch CA at all -- it only asserts the live guide text still documents
    the lifecycle, the format-group concept, and the error catalog. Kept
    resilient to wording tweaks: presence of a few stable keywords, not
    full-text equality.

    Args:
        ca: Unused; ``info`` has no CA-side dependency.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: Unused; kept for the uniform scenario_fns signature.

    Returns:
        Evidence payload with the guide length and which anchors matched.
    """
    del ca, args, watch_dir_id
    response = await _call(ed, "info", {})
    guide_text = response.get("markdown")
    if not isinstance(guide_text, str) or not guide_text.strip():
        guide_text = json.dumps(response, ensure_ascii=False)
    lowered = guide_text.lower()

    lifecycle_words = ("open", "preview", "edit", "write", "close")
    missing_lifecycle = [word for word in lifecycle_words if word not in lowered]
    if missing_lifecycle:
        raise PipelineFailure(
            "info guide missing lifecycle keyword(s)",
            {"missing": missing_lifecycle, "guide_excerpt": guide_text[:2000]},
        )
    if "format group" not in lowered:
        raise PipelineFailure(
            "info guide missing format-group marker",
            {"guide_excerpt": guide_text[:2000]},
        )
    if "error" not in lowered or "validation_error" not in lowered:
        raise PipelineFailure(
            "info guide missing error-catalog marker",
            {"guide_excerpt": guide_text[:2000]},
        )
    return {
        "guide_length": len(guide_text),
        "lifecycle_words_present": list(lifecycle_words),
        "format_group_marker_present": True,
        "error_catalog_marker_present": True,
        "registered_commands": response.get("registered_commands"),
    }


async def _scenario_python_header_comment(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Live regression for bug 86288c9c (Python class header trailing comment).

    Also live-verifies ``universal_file_search`` and
    ``universal_file_node_at_line`` (own-command coverage, 2026-07-24):
    piggybacked on the same open session -- no new fixtures. A simple
    ``ClassDef``/``name=Foo`` search must resolve the SAME node_ref that
    preview's class block located. A node-at-line lookup on the class header
    line resolves the MOST SPECIFIC node there (the ``Foo`` Name token, not
    the class itself); with ``include_ancestors=true`` the class node_ref
    must appear among its ancestors, proving both commands are anchored to
    the same session tree position as preview.
    """
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
        # _find_preview_node_ref walks the WHOLE payload and can match a node
        # whose "text" merely CONTAINS "class Foo" as a rendered substring
        # (e.g. the module's first-statement "focus" node, whose text is the
        # full-file rendering) instead of the actual ClassDef -- the same
        # failure mode documented on _find_class_block_node_ref below
        # (bdce5d39 evidence). Use the block-restricted lookup instead so
        # class_ref is the class block's own node_ref, matching what
        # universal_file_search/universal_file_node_at_line resolve.
        class_ref = _find_class_block_node_ref(preview, "class Foo")
        if not class_ref:
            raise PipelineFailure("preview did not expose class Foo node_ref", preview)

        search_result = await _call(
            ed,
            "universal_file_search",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "search_type": "simple",
                "node_type": "ClassDef",
                "name": "Foo",
                "require_one": True,
            },
        )
        search_node_ref_raw = search_result.get("node_ref")
        search_node_ref = (
            str(search_node_ref_raw) if search_node_ref_raw is not None else None
        )
        if search_node_ref != class_ref:
            raise PipelineFailure(
                "universal_file_search did not resolve the preview-located "
                "class Foo node_ref",
                {
                    "search_node_ref": search_node_ref,
                    "class_ref": class_ref,
                    "search_result": search_result,
                },
            )

        # Line 3 of initial_content is the "class Foo:  # type: ignore[misc]"
        # header. node_at_line resolves the MOST SPECIFIC node on that line,
        # which is the "Foo" Name token nested inside the ClassDef -- NOT the
        # ClassDef itself (confirmed live: node_ref_kind="uuid", type="Name").
        # include_ancestors=true additionally returns covering nodes smallest
        # span first; the ClassDef -- the SAME node preview/search located --
        # must be among them, proving node_at_line is anchored to the same
        # tree position rather than requiring the top-level ref to equal the
        # (necessarily larger-span) class ref directly.
        class_header_line = 3
        node_at_line_result = await _call(
            ed,
            "universal_file_node_at_line",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "line": class_header_line,
                "include_ancestors": True,
            },
        )
        node_at_line_ref_raw = node_at_line_result.get("node_ref")
        node_at_line_ref = (
            str(node_at_line_ref_raw) if node_at_line_ref_raw is not None else None
        )
        ancestors = node_at_line_result.get("ancestors")
        class_ancestor_ref = None
        if isinstance(ancestors, list):
            for ancestor in ancestors:
                if not isinstance(ancestor, dict):
                    continue
                ancestor_ref_raw = ancestor.get("node_ref")
                ancestor_ref = (
                    str(ancestor_ref_raw) if ancestor_ref_raw is not None else None
                )
                if (
                    ancestor_ref == class_ref
                    and str(ancestor.get("type") or "") == "ClassDef"
                ):
                    class_ancestor_ref = ancestor_ref
                    break
        if class_ancestor_ref != class_ref:
            raise PipelineFailure(
                "universal_file_node_at_line ancestors did not include the "
                "preview-located class Foo node_ref",
                {
                    "node_at_line_ref": node_at_line_ref,
                    "class_ref": class_ref,
                    "line": class_header_line,
                    "node_at_line_result": node_at_line_result,
                },
            )

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
            "search_node_ref": search_node_ref,
            "search_total_matches": search_result.get("total_matches"),
            "node_at_line_ref": node_at_line_ref,
            "node_at_line_type": node_at_line_result.get("type"),
            "node_at_line_class_ancestor_ref": class_ancestor_ref,
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
            retry_on_transport_error=True,
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
            retry_on_transport_error=True,
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
                '"""Live verifier sibling module fixture."""\n' "\n" "VALUE = 42\n"
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
            retry_on_transport_error=True,
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
        importer_commit = await _call(
            ed,
            "universal_file_write",
            commit_params,
            retry_on_transport_error=True,
        )
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


def _extract_error_message(evidence: Any) -> str:
    """Extract the upstream error message from a JSON-RPC evidence payload.

    Unlike ``_find_nested_str`` (which is designed to skip blank strings while
    hunting for IDs), this preserves emptiness on purpose: bug 84d93cca was
    exactly an upstream error whose ``message`` field existed but was blank,
    and the live regression must be able to tell that apart from a populated
    message.

    Args:
        evidence: Raw JSON-RPC response dict captured on a caught PipelineFailure
            or client exception (may be None or a non-dict payload).

    Returns:
        The most specific ``message`` string found in ``error``/``data.error``,
        or "" when no such field exists.
    """
    if not isinstance(evidence, dict):
        return ""
    data = evidence.get("data")
    if isinstance(data, dict):
        inner = data.get("error")
        if isinstance(inner, dict) and "message" in inner:
            return str(inner.get("message") or "")
        if isinstance(inner, str):
            return inner
    top = evidence.get("error")
    if isinstance(top, dict) and "message" in top:
        return str(top.get("message") or "")
    if isinstance(top, str):
        return top
    return ""


def _extract_error_code(evidence: Any) -> str | None:
    """Extract the upstream error code from a JSON-RPC evidence payload.

    Mirrors ``_extract_error_message``'s traversal of ``data.error``/``error``,
    but reads the ``code`` field instead of ``message``.

    Args:
        evidence: Raw JSON-RPC response dict captured on a caught
            ``PipelineFailure`` (may be None or a non-dict payload).

    Returns:
        The most specific ``code`` string found, or None when absent.
    """
    if not isinstance(evidence, dict):
        return None
    data = evidence.get("data")
    if isinstance(data, dict):
        inner = data.get("error")
        if isinstance(inner, dict) and inner.get("code"):
            return str(inner["code"])
    top = evidence.get("error")
    if isinstance(top, dict) and top.get("code"):
        return str(top["code"])
    return None


async def _scenario_open_queue_autopoll(
    ca: JsonRpcClient,
    ed: JsonRpcClient,
    args: argparse.Namespace,
    watch_dir_id: str,
) -> dict[str, Any]:
    """Live regression for bug 84d93cca (OPEN_ERROR / queued-job auto_poll survival).

    On the current degraded casmgr, CA list_project_files sync-scan for a
    project at this project's on-disk scale (ai-editor itself -- a throwaway
    fixture project is too small to reproduce the symptom) can exceed the
    adapter's 90s sync cap, forcing a queued-job handoff on
    universal_file_open. The 1.0.65 client MUST survive this via unified
    auto_poll (or its legacy-polling fallback) instead of surfacing the
    historical empty-message OPEN_ERROR.

    Wall time is measured and RECORDED, not hidden: on this known-degraded
    server ~2 minutes is an acceptable, logged duration, not a failure.
    A failed open is likewise acceptable evidence as long as its error
    message is non-empty; only an EMPTY error message reproduces bug
    84d93cca and fails this scenario.

    Args:
        ca: JSON-RPC client for the Code Analysis server (used for CA
            session_create/session_delete only).
        ed: Unused default-timeout AI Editor client; this scenario builds its
            own patient (>=360s) client because the degraded sync path can
            take longer than the pipeline's default 120s.
        args: Parsed pipeline arguments (hosts, ports, mtls paths).
        watch_dir_id: unused; kept for the uniform scenario_fns signature.

    Returns:
        Evidence payload with wall-clock timing and the open/close outcome.
    """
    del ed
    del watch_dir_id
    project_id = "3509ae38-0f02-4f16-8e44-e6de7ca0c050"  # ai-editor itself
    # Stable repo file; moved from prompts/claude/roles/laws.yaml to
    # docs/agent-ref/roles/laws.yaml by commit 950f1d9 (same content, new path).
    file_path = "docs/agent-ref/roles/laws.yaml"
    session_id = await _create_session(ca, "84d93cca_open_queue_autopoll")
    ed_patient = _client(
        args.editor_host, args.editor_port, args.mtls_dir, timeout=360.0
    )

    start = time.monotonic()
    open_response: dict[str, Any] | None = None
    error_message: str | None = None
    try:
        raw = await ed_patient.execute_command_unified(
            "universal_file_open",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
            },
            auto_poll=True,
            timeout=360.0,
        )
        open_response = _unwrap(raw)
    except PipelineFailure as exc:
        error_message = _extract_error_message(exc.evidence) or str(exc)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - transport/timeout evidence, not control flow
        error_message = str(exc) or repr(exc)
    wall_seconds = time.monotonic() - start

    if error_message is not None and not error_message.strip():
        raise PipelineFailure(
            "universal_file_open failed with an EMPTY error message "
            "(historical OPEN_ERROR regression, bug 84d93cca)",
            {
                "open_wall_seconds": wall_seconds,
                "project_id": project_id,
                "file_path": file_path,
            },
        )

    close_result: dict[str, Any] | None = None
    if error_message is None:
        close_result = await _close_suppress(
            ed_patient, project_id, session_id, file_path
        )

    session_delete_error: str | None = None
    try:
        await _call(ca, "session_delete", {"session_id": session_id})
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup, not an assertion
        session_delete_error = repr(exc)

    return {
        "project_id": project_id,
        "file_path": file_path,
        "session_id": session_id,
        "open_wall_seconds": round(wall_seconds, 3),
        "open_error": error_message,
        "open_response_keys": (
            sorted(open_response.keys()) if isinstance(open_response, dict) else None
        ),
        "close": _jsonable(close_result),
        "session_delete_error": session_delete_error,
    }


_B215FBD3_YAML_FIXTURE = (
    "# Fresh fixture for ai-editor tree-temp YAML round-trip re-verification (2026-07-23)\n"
    'name: "abc-123"  # inline comment on name\n'
    "flow_map: { a: 1, b: 2 }\n"
    "flow_list: [10, 20, 30]\n"
    "target: original\n"
)


async def _scenario_styled_yaml_minimal_diff(
    ca: JsonRpcClient,
    ed: JsonRpcClient,
    args: argparse.Namespace,
    watch_dir_id: str,
) -> dict[str, Any]:
    """Live regression for bug b215fbd3 (tree-temp YAML full-file rewrite fidelity).

    A single scalar mutation on a styled YAML fixture (banner comment, inline
    comment, double-quoted string, flow-style mapping, flow-style list) must
    commit with a MINIMAL diff: only the mutated ``target`` line changes,
    tolerating ONLY the documented interior flow-map padding normalization
    (``{ a: 1, b: 2 }`` -> ``{a: 1, b: 2}``).

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments (hosts, ports, mtls paths); unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the committed content and the per-line diff check.
    """
    del args
    scenario_slug = "b215fbd3_styled_yaml"
    file_path = "verify/styled_yaml_minimal_diff.yaml"
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
            "initial_content": _B215FBD3_YAML_FIXTURE,
        },
    )
    try:
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {"type": "replace", "json_pointer": "/target", "value": "changed"}
                ],
            },
        )
        preview_write = await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "preview",
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
                "verify_after_upload": True,
            },
            retry_on_transport_error=True,
        )
        if not commit.get("uploaded"):
            raise PipelineFailure("styled YAML commit did not upload changes", commit)
        ca_verify = commit.get("ca_verify") or {}
        if ca_verify and ca_verify.get("ok") is False:
            raise PipelineFailure("styled YAML commit ca_verify failed", commit)

        # No hardcoded end_line: a lossy rewrite can shrink the file below any
        # fixed bound and a fixed range would then raise INVALID_RANGE instead
        # of letting the assertions below report the actual content diff.
        content = await _read_file_text(ca, project_id, file_path)

        required_substrings = (
            "# Fresh fixture for ai-editor tree-temp YAML round-trip re-verification (2026-07-23)",
            "# inline comment on name",
            'name: "abc-123"',
            "flow_list: [10, 20, 30]",
            "target: changed",
        )
        missing = [needle for needle in required_substrings if needle not in content]
        if missing:
            raise PipelineFailure(
                "styled YAML round-trip lost required fixture content",
                {"missing": missing, "content": content},
            )
        if (
            "flow_map: { a: 1, b: 2 }" not in content
            and "flow_map: {a: 1, b: 2}" not in content
        ):
            raise PipelineFailure(
                "styled YAML round-trip broke flow-style flow_map", {"content": content}
            )
        if "target: original" in content:
            raise PipelineFailure(
                "styled YAML round-trip did not apply the target mutation",
                {"content": content},
            )

        expected_lines = _B215FBD3_YAML_FIXTURE.splitlines()
        actual_lines = content.splitlines()
        if len(actual_lines) != len(expected_lines):
            raise PipelineFailure(
                "styled YAML round-trip changed the line count",
                {"expected_lines": expected_lines, "actual_lines": actual_lines},
            )
        unexpected_diffs = []
        for index, (expected_line, actual_line) in enumerate(
            zip(expected_lines, actual_lines)
        ):
            if expected_line == actual_line:
                continue
            if expected_line == "target: original" and actual_line == "target: changed":
                continue
            if (
                expected_line == "flow_map: { a: 1, b: 2 }"
                and actual_line == "flow_map: {a: 1, b: 2}"
            ):
                continue
            unexpected_diffs.append(
                {"line": index + 1, "expected": expected_line, "actual": actual_line}
            )
        if unexpected_diffs:
            raise PipelineFailure(
                "styled YAML round-trip changed a line beyond the mutated scalar "
                "and the documented flow-map padding normalization",
                {"unexpected_diffs": unexpected_diffs, "content": content},
            )

        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "edit": _jsonable(edit),
            "preview_has_changes": preview_write.get("has_changes"),
            "commit_uploaded": commit.get("uploaded"),
            "ca_verify": commit.get("ca_verify"),
            "readback_content": content,
            "cleanup": (
                "temp fixture file left under its throwaway per-scenario CA "
                "project (pipeline convention: no dedicated per-file delete)"
            ),
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_71D29A80_TOML_FIXTURE = (
    "[project]\n"
    'name = "ai-editor"\n'
    'version = "1.0.77"\n'
    'description = "AI Editor MCP server: universal file preview, open, edit, '
    'write, and close"\n'
    'readme = { file = "docs/README.md", content-type = "text/markdown" }\n'
    'requires-python = ">=3.10"\n'
    "dependencies = [\n"
    '    "python-dotenv>=1.0",\n'
    '    "pyyaml>=6.0",\n'
    '    "click>=8.0",\n'
    '    "mcp>=1.0.0",\n'
    "]\n"
)


async def _scenario_toml_valid_open_71d29a80(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 71d29a80: a pyproject.toml-shaped fixture must open as valid TOML.

    Reproduces ai-editor's OWN pyproject.toml constructs: an inline table
    (``readme = { file = ..., content-type = ... }``) together with a
    multi-line array of strings (``dependencies = [...]``). Live 1.0.77
    wrongly falls back to text mode, reporting "Invalid TOML value: Invalid
    value (at end of document)" via ``fallback_reason`` -- a construct that
    is unambiguously valid TOML (importable with ``tomllib.loads`` directly).
    This check FAILS whenever ``universal_file_open`` reports ``is_invalid``
    or a non-empty ``fallback_reason`` for this fixture.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the open response's format_group/is_invalid.
    """
    del args
    scenario_slug = "71d29a80_toml_valid_open"
    file_path = "verify/71d29a80_pyproject_shape.toml"
    project = await _create_project(ca, watch_dir_id, scenario_slug)
    project_id = project["project_id"]
    session_id = await _create_session(ca, scenario_slug)
    open_response = await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "create": True,
            "initial_content": _71D29A80_TOML_FIXTURE,
        },
    )
    try:
        is_invalid = open_response.get("is_invalid")
        fallback_reason = open_response.get("fallback_reason")
        if is_invalid or fallback_reason:
            raise PipelineFailure(
                "universal_file_open reported is_invalid/fallback_reason for a "
                "valid pyproject.toml-shaped TOML fixture (bug 71d29a80)",
                {
                    "is_invalid": is_invalid,
                    "fallback_reason": fallback_reason,
                    "format_group": open_response.get("format_group"),
                    "open_response": open_response,
                },
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "format_group": open_response.get("format_group"),
            "is_invalid": is_invalid,
            "fallback_reason": fallback_reason,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_91B8CE0B_GITIGNORE_FIXTURE = (
    "# verify_editor_ca_chain fixture: .gitignore-style extensionless file\n"
    "*.pyc\n"
    "__pycache__/\n"
    ".venv/\n"
)


async def _scenario_extensionless_open_91b8ce0b(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 91b8ce0b: a `.gitignore`-style extensionless file must open as text.

    ``Path(".gitignore").suffix`` is empty, so the handler registry has no
    extension to key off. Expected behavior: an extensionless dotfile is a
    routine text file and should open successfully in text/line mode WITHOUT
    requiring the caller to pass ``format_group`` as a hint. Live 1.0.77
    instead rejects the open with ``UNKNOWN_FORMAT`` unless ``format_group``
    is explicitly supplied. This check FAILS when the open response's error
    code is ``UNKNOWN_FORMAT``.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the open response's format_group.
    """
    del args
    scenario_slug = "91b8ce0b_extensionless_open"
    file_path = "verify/.gitignore"
    project = await _create_project(ca, watch_dir_id, scenario_slug)
    project_id = project["project_id"]
    session_id = await _create_session(ca, scenario_slug)
    try:
        open_response = await _call(
            ed,
            "universal_file_open",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "create": True,
                "initial_content": _91B8CE0B_GITIGNORE_FIXTURE,
            },
        )
    except PipelineFailure as exc:
        error_code = _extract_error_code(exc.evidence)
        if error_code == "UNKNOWN_FORMAT":
            raise PipelineFailure(
                "universal_file_open rejected an extensionless .gitignore-style "
                "file with UNKNOWN_FORMAT instead of a text-mode open "
                "(bug 91b8ce0b)",
                {
                    "error_code": error_code,
                    "error_message": _extract_error_message(exc.evidence),
                    "evidence": exc.evidence,
                },
            ) from exc
        raise
    try:
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "format_group": open_response.get("format_group"),
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


async def _scenario_created_draft_trailing_newline_62759f8a(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 62759f8a: a freshly-created module inserted via code_lines must commit
    with a trailing newline.

    Opens a brand-new .py file (create=True, minimal placeholder content),
    inserts a minimal valid module -- a module docstring plus one function
    with a Google-style docstring -- via ``universal_file_edit`` at
    ``parent_node_id="__root__"``, then commits. Expected behavior: the
    committed file ends with a newline, matching PEP 8/flake8 W292. Live
    1.0.77 assembles the inserted ``code_lines`` without a final newline and
    the commit is rejected by the server's own flake8 quality gate with W292
    ("no newline at end of file") -- the server fails its own pre-write
    validation on output it produced itself. This check FAILS when the
    commit is rejected with an error mentioning W292/"no newline at end of
    file"; it PASSES when the commit clears the server's own flake8 gate
    (which enforces the trailing newline byte) and a CA readback returns
    the inserted module content. NOTE: ``get_file_lines`` joins line rows
    and can never represent the EOF newline itself, so the gate verdict is
    the byte-level assertion here, not ``content.endswith``.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the commit outcome and trailing-newline check.
    """
    del args
    scenario_slug = "62759f8a_trailing_newline"
    file_path = "verify/62759f8a_trailing_newline.py"
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
            "initial_content": "",
        },
    )
    try:
        module_code_lines = [
            '"""Module docstring for the 62759f8a trailing-newline fixture."""',
            "",
            "",
            "def compute_value() -> int:",
            '    """Return the fixture value.',
            "",
            "    Returns:",
            "        Fixture value.",
            '    """',
            "    return 1",
        ]
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "insert",
                        "parent_node_id": "__root__",
                        "position": "last",
                        "code_lines": module_code_lines,
                    }
                ],
            },
        )
        try:
            commit = await _call(
                ed,
                "universal_file_write",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                    "write_mode": "commit",
                },
                retry_on_transport_error=True,
            )
        except PipelineFailure as exc:
            # The W292 detail lives inside error.data.validation_results, not
            # in the top-level error message -- search the WHOLE evidence
            # payload for the symptom, not just _extract_error_message's
            # top-level message, so this branch does not silently fall
            # through to a generic re-raise on a real symptom match.
            evidence_text = json.dumps(exc.evidence, ensure_ascii=False).lower()
            if "w292" in evidence_text or "no newline at end of file" in evidence_text:
                raise PipelineFailure(
                    "commit of a freshly-inserted module was rejected by the "
                    "server's own flake8 gate for missing a trailing newline "
                    "(bug 62759f8a)",
                    {
                        "error_code": _extract_error_code(exc.evidence),
                        "error_message": _extract_error_message(exc.evidence),
                        "evidence": exc.evidence,
                    },
                ) from exc
            raise
        if not commit.get("uploaded"):
            raise PipelineFailure(
                "created-draft module commit did not upload changes", commit
            )
        content = await _read_file_text(ca, project_id, file_path, end_line=20)
        if not content.strip():
            raise PipelineFailure(
                "CA readback of the committed module returned no content "
                "(bug 62759f8a)",
                {"content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "edit": _jsonable(edit),
            "commit_uploaded": commit.get("uploaded"),
            "flake8_gate_cleared": True,
            "readback_excerpt": content[:1000],
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


async def _scenario_create_draft_discard_close_2e44a0a9(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 2e44a0a9: closing a never-committed new-file draft must discard,
    not reject with MODIFIED_NOT_WRITTEN.

    Opens a brand-new .py file (create=True), modifies the draft via
    ``universal_file_edit`` insert, then closes WITHOUT committing --
    requesting the discard path via ``discard=true`` if the API accepts it,
    else a plain ``universal_file_close`` call. Per ai-editor's own
    documented contract for new files (R1/R3): "a file opened with
    create=true is held only in the local workspace until its first
    universal_file_write commit ... Closing such a file before any commit
    releases no CA lock and simply discards the draft." Live 1.0.77
    contradicts its own documented contract: ``universal_file_close``
    gates on ``session.modified`` BEFORE checking whether the file was ever
    persisted to CA, so closing an uncommitted new-file draft is rejected
    with MODIFIED_NOT_WRITTEN exactly like an edit to an existing committed
    file. This check FAILS when the close is rejected with
    MODIFIED_NOT_WRITTEN.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload including any API surprise from a discard=true probe.
    """
    del args
    scenario_slug = "2e44a0a9_create_draft_discard_close"
    file_path = "verify/2e44a0a9_discard_close.py"
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
            "initial_content": '"""Module docstring for the 2e44a0a9 discard-close fixture."""\n',
        },
    )
    close_attempted = False
    try:
        await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "insert",
                        "parent_node_id": "__root__",
                        "position": "last",
                        "code_lines": ["", "NEVER_COMMITTED = 1"],
                    }
                ],
            },
        )

        # API surprise probe: does universal_file_close accept a discard=true
        # parameter at all? Recorded regardless of outcome; the schema is
        # additionalProperties: False so this is expected to be rejected at
        # parameter-validation with a VALIDATION_ERROR (not MODIFIED_NOT_WRITTEN)
        # rather than actually performing a discard.
        discard_probe: dict[str, Any] = {"attempted": True}
        try:
            discard_response = await _call(
                ed,
                "universal_file_close",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                    "discard": True,
                },
            )
            discard_probe["accepted"] = True
            discard_probe["response"] = discard_response
            close_attempted = True
        except PipelineFailure as exc:
            discard_probe["accepted"] = False
            discard_probe["error_code"] = _extract_error_code(exc.evidence)
            discard_probe["error_message"] = _extract_error_message(exc.evidence)

        if discard_probe["accepted"]:
            return {
                **project,
                "session_id": session_id,
                "file_path": file_path,
                "discard_probe": discard_probe,
                "close_path": "discard=true accepted directly",
            }

        # Fall back to a plain close: no discard parameter, no
        # write_before_close -- the never-committed draft should simply be
        # discarded per the documented new-file (R1/R3) close contract.
        try:
            close_response = await _call(
                ed,
                "universal_file_close",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
            close_attempted = True
        except PipelineFailure as exc:
            error_code = _extract_error_code(exc.evidence)
            if error_code == "MODIFIED_NOT_WRITTEN":
                raise PipelineFailure(
                    "closing a never-committed new-file draft was rejected "
                    "with MODIFIED_NOT_WRITTEN instead of discarding it "
                    "(bug 2e44a0a9)",
                    {
                        "discard_probe": discard_probe,
                        "error_code": error_code,
                        "error_message": _extract_error_message(exc.evidence),
                        "evidence": exc.evidence,
                    },
                ) from exc
            raise
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "discard_probe": discard_probe,
            "close_path": "plain close (no discard param, no write_before_close)",
            "close_response": close_response,
        }
    finally:
        if not close_attempted:
            # Best-effort cleanup only: write_before_close=true commits and
            # closes so the throwaway project does not leak an open session.
            # Never raised from the scenario -- this is not part of the
            # assertion above.
            try:
                await asyncio.wait_for(
                    _call(
                        ed,
                        "universal_file_close",
                        {
                            "project_id": project_id,
                            "session_id": session_id,
                            "file_path": file_path,
                            "write_before_close": True,
                        },
                    ),
                    timeout=DEFAULT_CLOSE_TIMEOUT_SECONDS,
                )
            except Exception:  # noqa: BLE001 - cleanup only
                pass


_831A82BE_PY_FIXTURE = (
    '"""Fixture module for bug 831a82be (FunctionDef replace no-nesting)."""\n'
    "\n"
    "\n"
    "def first_function() -> int:\n"
    '    """Return the first fixture value.\n'
    "\n"
    "    Returns:\n"
    "        First fixture value.\n"
    '    """\n'
    "    return 1\n"
    "\n"
    "\n"
    "def second_function() -> int:\n"
    '    """Return the second fixture value.\n'
    "\n"
    "    Returns:\n"
    "        Second fixture value.\n"
    '    """\n'
    "    return 2\n"
)


async def _scenario_py_replace_functiondef_no_nesting_831a82be(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 831a82be: replacing a top-level FunctionDef by node_ref must not
    nest it inside the function it replaces.

    Two module-level functions are fixtures; ``universal_file_search``
    resolves the SECOND function's node_ref (mirrors the bug's own repro: two
    top-level FunctionDef node_refs obtained via search, then a batch
    ``replace`` targeting them). ``universal_file_edit`` replaces
    ``second_function`` with a differently-bodied implementation of the SAME
    name. Live 1.0.69 inserted the new definition NESTED inside the old
    function's body instead of replacing the module-level statement, with the
    old body's tail surviving after the nested copy. This check FAILS when
    the committed file contains more than one ``def second_function``, when
    that definition is indented (nested) rather than at module level, or when
    the original body (``return 2``) survives; it PASSES only when the
    function is replaced cleanly at module level.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the search node_ref, edit result, and readback.
    """
    del args
    scenario_slug = "831a82be_functiondef_no_nesting"
    file_path = "verify/831a82be_functiondef_no_nesting.py"
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
            "initial_content": _831A82BE_PY_FIXTURE,
        },
    )
    try:
        search_result = await _call(
            ed,
            "universal_file_search",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "search_type": "simple",
                "node_type": "FunctionDef",
                "name": "second_function",
                "require_one": True,
            },
        )
        node_ref_raw = search_result.get("node_ref")
        node_ref = str(node_ref_raw) if node_ref_raw is not None else None
        if not node_ref:
            raise PipelineFailure(
                "universal_file_search did not resolve second_function's node_ref",
                search_result,
            )
        replacement_code_lines = [
            "def second_function() -> int:",
            '    """Return the replaced fixture value.',
            "",
            "    Returns:",
            "        Replaced fixture value.",
            '    """',
            "    return 99",
        ]
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "replace",
                        "node_id": node_ref,
                        "code_lines": replacement_code_lines,
                    }
                ],
            },
        )
        await _call(
            ed,
            "universal_file_write",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "write_mode": "preview",
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
            retry_on_transport_error=True,
        )
        if not commit.get("uploaded"):
            raise PipelineFailure(
                "second_function replace commit did not upload changes", commit
            )
        content = await _read_file_text(ca, project_id, file_path)
        def_lines = [
            line for line in content.splitlines() if "def second_function" in line
        ]
        def_count = len(def_lines)
        indents = [len(line) - len(line.lstrip(" ")) for line in def_lines]
        if def_count != 1 or any(indent != 0 for indent in indents):
            raise PipelineFailure(
                "replaced FunctionDef was nested instead of replacing the "
                "module-level statement (bug 831a82be)",
                {
                    "def_second_function_count": def_count,
                    "indents": indents,
                    "content": content,
                },
            )
        if "return 2" in content:
            raise PipelineFailure(
                "original second_function body survived the replace "
                "(bug 831a82be)",
                {"content": content},
            )
        if "return 99" not in content:
            raise PipelineFailure(
                "replaced second_function body missing from CA readback",
                {"content": content},
            )
        if "def first_function" not in content or "return 1" not in content:
            raise PipelineFailure(
                "untouched first_function was corrupted by the replace",
                {"content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "search_node_ref": node_ref,
            "edit": _jsonable(edit),
            "commit_uploaded": commit.get("uploaded"),
            "def_second_function_count": def_count,
            "readback_content": content,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_5495F4BE_PY_FIXTURE = (
    '"""Fixture module for bug 5495f4be (leading comment preservation on '
    'replace)."""\n'
    "\n"
    "# fixture: standalone comment above the constant\n"
    "# second line of the comment block\n"
    "CONST_VALUE = 1\n"
)


async def _scenario_py_replace_keeps_leading_comments_5495f4be(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 5495f4be: replacing a SimpleStatementLine must not drop its
    leading standalone comment block.

    A two-line standalone comment sits directly above a module-level
    ``CONST_VALUE = 1`` statement. ``universal_file_edit`` replaces that SAME
    statement (not the comment) with a new value, keeping the module valid
    Python -- the same replace shape as the bug's own repro (a
    SimpleStatementLine replace via ``code_lines``). Live 1.0.69 silently
    dropped leading comment trivia when replacing the statement below it.
    This check FAILS when either original comment line is missing from the
    committed file; it PASSES only when both comment lines and the new value
    are present.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the located statement node_ref and readback.
    """
    del args
    scenario_slug = "5495f4be_leading_comment_preservation"
    file_path = "verify/5495f4be_leading_comment_preservation.py"
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
            "initial_content": _5495F4BE_PY_FIXTURE,
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
        stmt_ref = _find_smallest_preview_node_ref(preview, "CONST_VALUE = 1")
        if not stmt_ref:
            raise PipelineFailure(
                "preview did not expose CONST_VALUE statement node_ref", preview
            )
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "replace",
                        "node_id": stmt_ref,
                        "code_lines": ["CONST_VALUE = 2"],
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
            retry_on_transport_error=True,
        )
        if not commit.get("uploaded"):
            raise PipelineFailure(
                "CONST_VALUE replace commit did not upload changes", commit
            )
        content = await _read_file_text(ca, project_id, file_path)
        required_substrings = (
            "# fixture: standalone comment above the constant",
            "# second line of the comment block",
            "CONST_VALUE = 2",
        )
        missing = [needle for needle in required_substrings if needle not in content]
        if missing:
            raise PipelineFailure(
                "leading standalone comment block was dropped by the replace "
                "(bug 5495f4be)",
                {"missing": missing, "content": content},
            )
        if "CONST_VALUE = 1" in content:
            raise PipelineFailure(
                "original CONST_VALUE statement survived the replace",
                {"content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "stmt_node_ref": stmt_ref,
            "edit": _jsonable(edit),
            "commit_uploaded": commit.get("uploaded"),
            "readback_content": content,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_086A8F6C_PY_FIXTURE = (
    '"""Fixture module for bug 086a8f6c (search node_id/stable_id '
    'uniqueness)."""\n'
    "\n"
    "\n"
    "class Alpha:\n"
    '    """Alpha fixture class."""\n'
    "\n"
    "    def method_one(self) -> int:\n"
    '        """Return the Alpha fixture value.\n'
    "\n"
    "        Returns:\n"
    "            Alpha fixture value.\n"
    '        """\n'
    "        return 1\n"
    "\n"
    "\n"
    "class Beta:\n"
    '    """Beta fixture class."""\n'
    "\n"
    "    def method_two(self) -> int:\n"
    '        """Return the Beta fixture value.\n'
    "\n"
    "        Returns:\n"
    "            Beta fixture value.\n"
    '        """\n'
    "        return 2\n"
    "\n"
    "\n"
    "def standalone_one() -> int:\n"
    '    """Return the first standalone fixture value.\n'
    "\n"
    "    Returns:\n"
    "        First standalone fixture value.\n"
    '    """\n'
    "    return 10\n"
    "\n"
    "\n"
    "def standalone_two() -> int:\n"
    '    """Return the second standalone fixture value.\n'
    "\n"
    "    Returns:\n"
    "        Second standalone fixture value.\n"
    '    """\n'
    "    return 20\n"
)


async def _scenario_search_ids_unique_086a8f6c(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 086a8f6c: universal_file_search must not collide one node's
    stable_id with a DIFFERENT node's node_id.

    A fixture with two classes (one method each) and two standalone
    functions gives ``universal_file_search`` a tree with many distinct
    nodes, mirroring the bug's own repro shape (a ``simple`` search returning
    several def/statement nodes, as in the 86288c9c scenario's search call).
    Every match's ``node_id``, ``stable_id``, and ``node_ref`` is collected.
    Live 1.0.69 returned one node's ``stable_id`` equal to a DIFFERENT node's
    ``node_id``, making id-based addressing ambiguous and explaining
    downstream STALE_NODE_ID/wrong-node-replaced failures. This check FAILS
    when any identifier value is simultaneously the ``stable_id`` of one
    match and the ``node_id`` of a distinct match, or when any ``node_ref``
    value is shared by more than one distinct node.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the match count and any detected collisions.
    """
    del args
    scenario_slug = "086a8f6c_search_ids_unique"
    file_path = "verify/086a8f6c_search_ids_unique.py"
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
            "initial_content": _086A8F6C_PY_FIXTURE,
        },
    )
    try:
        search_result = await _call(
            ed,
            "universal_file_search",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "search_type": "simple",
            },
        )
        matches = search_result.get("matches")
        if not isinstance(matches, list) or len(matches) < 4:
            raise PipelineFailure(
                "universal_file_search returned too few matches to exercise "
                "id uniqueness (bug 086a8f6c)",
                search_result,
            )
        entries: list[dict[str, Any]] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            node_id = match.get("node_id")
            stable_id = match.get("stable_id")
            node_ref = match.get("node_ref")
            entries.append(
                {
                    "node_id": str(node_id) if node_id is not None else None,
                    "stable_id": str(stable_id) if stable_id is not None else None,
                    "node_ref": str(node_ref) if node_ref is not None else None,
                    "type": match.get("type"),
                    "start_line": match.get("start_line"),
                }
            )

        stable_vs_node_id_collisions = []
        for i, entry_i in enumerate(entries):
            for j, entry_j in enumerate(entries):
                if i == j:
                    continue
                if (
                    entry_i["stable_id"] is not None
                    and entry_i["stable_id"] == entry_j["node_id"]
                ):
                    stable_vs_node_id_collisions.append(
                        {"stable_id_owner": entry_i, "node_id_owner": entry_j}
                    )

        node_ref_owners: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            ref = entry["node_ref"]
            if ref is None:
                continue
            node_ref_owners.setdefault(ref, []).append(entry)
        duplicate_node_refs = {
            ref: owners
            for ref, owners in node_ref_owners.items()
            if len(owners) > 1 and len({owner["node_id"] for owner in owners}) > 1
        }

        if stable_vs_node_id_collisions or duplicate_node_refs:
            raise PipelineFailure(
                "universal_file_search returned colliding node identifiers "
                "across distinct nodes (bug 086a8f6c)",
                {
                    "stable_vs_node_id_collisions": stable_vs_node_id_collisions[:10],
                    "duplicate_node_refs": duplicate_node_refs,
                    "total_matches": len(entries),
                },
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "total_matches": len(entries),
            "sample_entries": entries[:10],
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_1DB1038B_PY_FIXTURE = (
    '"""Fixture module for bug 1db1038b (search-then-edit same-session '
    'stale id)."""\n'
    "\n"
    "\n"
    "def compute(query_object: int) -> int:\n"
    '    """Compute a value from the query object.\n'
    "\n"
    "    Args:\n"
    "        query_object: Input fixture value.\n"
    "\n"
    "    Returns:\n"
    "        Computed fixture value.\n"
    '    """\n'
    "    return query_object + query_object\n"
)


async def _scenario_search_stable_id_usable_in_edit_1db1038b(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 1db1038b: stable_ids from universal_file_search must be usable in
    the VERY NEXT universal_file_edit, unchanged session.

    ``universal_file_search`` for ``Name[name=query_object]`` resolves
    several matches (the parameter and its uses in ``return query_object +
    query_object``, mirroring the bug's own repro of three Name matches). The
    last two matches' ``stable_id`` values are passed straight into ONE
    ``universal_file_edit`` replace batch -- no intervening preview/search/
    edit call. Live 1.0.69 rejected one of the just-returned stable_ids with
    STALE_NODE_ID inside the SAME unchanged session tree. This check FAILS on
    a STALE_NODE_ID or UNKNOWN_NODE_REF error from that edit call; it PASSES
    when the batch applies and the commit uploads.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the search matches and edit/commit outcome.
    """
    del args
    scenario_slug = "1db1038b_search_stable_id_usable_in_edit"
    file_path = "verify/1db1038b_search_stable_id_usable_in_edit.py"
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
            "initial_content": _1DB1038B_PY_FIXTURE,
        },
    )
    try:
        search_result = await _call(
            ed,
            "universal_file_search",
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "search_type": "simple",
                "node_type": "Name",
                "name": "query_object",
            },
        )
        matches = search_result.get("matches")
        if not isinstance(matches, list) or len(matches) < 2:
            raise PipelineFailure(
                "universal_file_search returned fewer than 2 query_object "
                "Name matches",
                search_result,
            )
        target_matches = matches[-2:]
        stable_ids: list[str] = []
        for match in target_matches:
            stable_id = match.get("stable_id") if isinstance(match, dict) else None
            if not stable_id:
                raise PipelineFailure(
                    "a query_object search match had no stable_id", search_result
                )
            stable_ids.append(str(stable_id))

        try:
            edit = await _edit(
                ed,
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": stable_ids[0],
                            "code_lines": ["query_object"],
                        },
                        {
                            "type": "replace",
                            "node_id": stable_ids[1],
                            "code_lines": ["query_object"],
                        },
                    ],
                },
            )
        except PipelineFailure as exc:
            error_code = _extract_error_code(exc.evidence)
            if error_code in {"STALE_NODE_ID", "UNKNOWN_NODE_REF"}:
                raise PipelineFailure(
                    "a stable_id returned by the immediately-preceding "
                    "universal_file_search was rejected by universal_file_edit "
                    "in the SAME unchanged session (bug 1db1038b)",
                    {
                        "error_code": error_code,
                        "error_message": _extract_error_message(exc.evidence),
                        "stable_ids": stable_ids,
                        "evidence": exc.evidence,
                    },
                ) from exc
            raise

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
            retry_on_transport_error=True,
        )
        if not commit.get("uploaded"):
            raise PipelineFailure(
                "query_object replace batch commit did not upload changes", commit
            )
        content = await _read_file_text(ca, project_id, file_path)
        if "return query_object + query_object" not in content:
            raise PipelineFailure(
                "committed content lost the query_object expression",
                {"content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "stable_ids": stable_ids,
            "edit": _jsonable(edit),
            "commit_uploaded": commit.get("uploaded"),
            "readback_content": content,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


_20B4BA84_YAML_FIXTURE = (
    "# top comment\n"
    "service:\n"
    '  name: release-1668-check   # inline comment\n'
    "  ports:\n"
    "    - 8080  # http\n"
    "    - 8443  # https\n"
    "# trailing comment\n"
)


async def _scenario_yaml_trailing_doc_comment_20b4ba84(
    ca: JsonRpcClient, ed: JsonRpcClient, args: argparse.Namespace, watch_dir_id: str
) -> dict[str, Any]:
    """Bug 20b4ba84: a trailing document-level comment after a nested block
    sequence must not crash the YAML serializer.

    Fixture (verbatim from the bug record): a banner comment, a mapping
    whose scalar carries an inline comment, a nested block sequence whose
    LAST item also carries an inline comment, followed by a column-0
    document-level trailing comment. The parser's known footer-comment
    misattachment merges the trailing document comment into the last array
    item's ``comment_before`` while that item still carries its own
    ``comment_inline``; live 1.0.69/cas@bb15d22 serialization then crashed
    with ``'CommentToken' object is not iterable`` inside ruamel's
    ``yaml_key_comment_extend``. A minimal unrelated edit (``service.name``)
    is applied and committed. This check FAILS when the write/commit raises
    a serializer crash mentioning CommentToken/"not iterable"; it PASSES only
    when the commit succeeds AND the readback still contains both the
    trailing document comment and the last item's inline comment.

    Args:
        ca: JSON-RPC client for the Code Analysis server.
        ed: JSON-RPC client for the AI Editor server.
        args: Parsed pipeline arguments; unused.
        watch_dir_id: CA watch directory that hosts the throwaway project.

    Returns:
        Evidence payload with the commit outcome and readback content.
    """
    del args
    scenario_slug = "20b4ba84_yaml_trailing_doc_comment"
    file_path = "verify/20b4ba84_yaml_trailing_doc_comment.yaml"
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
            "initial_content": _20B4BA84_YAML_FIXTURE,
        },
    )
    try:
        edit = await _edit(
            ed,
            {
                "project_id": project_id,
                "session_id": session_id,
                "file_path": file_path,
                "operations": [
                    {
                        "type": "replace",
                        "json_pointer": "/service/name",
                        "value": "release-1669-check",
                    }
                ],
            },
        )
        try:
            preview_write = await _call(
                ed,
                "universal_file_write",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "file_path": file_path,
                    "write_mode": "preview",
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
                    "verify_after_upload": True,
                },
                retry_on_transport_error=True,
            )
        except PipelineFailure as exc:
            evidence_text = json.dumps(exc.evidence, ensure_ascii=False)
            message = _extract_error_message(exc.evidence)
            haystack = f"{message}\n{evidence_text}".lower()
            if "commenttoken" in haystack or "not iterable" in haystack:
                raise PipelineFailure(
                    "YAML write/commit crashed serializing a trailing "
                    "document-level comment merged onto a commented last "
                    "array item (bug 20b4ba84)",
                    {
                        "error_code": _extract_error_code(exc.evidence),
                        "error_message": message,
                        "evidence": exc.evidence,
                    },
                ) from exc
            raise
        if not commit.get("uploaded"):
            raise PipelineFailure(
                "20b4ba84 minimal edit commit did not upload changes", commit
            )
        ca_verify = commit.get("ca_verify") or {}
        if isinstance(ca_verify, dict) and not ca_verify.get("verified"):
            raise PipelineFailure("20b4ba84 commit ca_verify failed", commit)

        content = await _read_file_text(ca, project_id, file_path)
        required_substrings = (
            "# top comment",
            "# inline comment",
            "release-1669-check",
            "# http",
            "# https",
            "# trailing comment",
        )
        missing = [needle for needle in required_substrings if needle not in content]
        if missing:
            raise PipelineFailure(
                "YAML round-trip lost required comment(s) (bug 20b4ba84)",
                {"missing": missing, "content": content},
            )
        if "release-1668-check" in content:
            raise PipelineFailure(
                "YAML round-trip did not apply the minimal edit",
                {"content": content},
            )
        return {
            **project,
            "session_id": session_id,
            "file_path": file_path,
            "edit": _jsonable(edit),
            "preview_has_changes": preview_write.get("has_changes"),
            "commit_uploaded": commit.get("uploaded"),
            "ca_verify": commit.get("ca_verify"),
            "readback_content": content,
        }
    finally:
        await _close_suppress(ed, project_id, session_id, file_path)


async def _run_scenario(
    name: str,
    fn: ScenarioFn,
    ca: JsonRpcClient,
    ed: JsonRpcClient,
    args: argparse.Namespace,
    watch_dir_id: str,
) -> dict[str, Any]:
    _progress(f"START {name}")
    try:
        details = await fn(ca, ed, args, watch_dir_id)
        result = {"name": name, "status": "passed", "details": _jsonable(details)}
        _progress(f"PASS  {name}")
        return result
    except PipelineFailure as exc:
        result = {
            "name": name,
            "status": "failed",
            "error": str(exc),
            "details": _jsonable(exc.evidence),
        }
        _progress(f"FAIL  {name}: {exc}")
        return result
    except Exception as exc:  # noqa: BLE001
        result = {
            "name": name,
            "status": "failed",
            "error": repr(exc),
            "details": traceback.format_exc(),
        }
        _progress(f"FAIL  {name}: {exc!r}")
        return result


def _scenario_registry() -> list[tuple[str, ScenarioFn]]:
    return [
        ("info_guide_smoke", _scenario_info_guide_smoke),
        ("296e02c9_edit_preview_commit_readback", _scenario_edit_preview_text),
        ("690f768c_yaml_root_key_parent_empty_and_slash", _scenario_yaml_root_insert),
        (
            "45b27a37_yaml_create_noop_commit_fidelity",
            _scenario_45b27a37_yaml_create_noop_commit_fidelity,
        ),
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
        (
            "open_queue_autopoll_84d93cca",
            _scenario_open_queue_autopoll,
        ),
        (
            "styled_yaml_minimal_diff_b215fbd3",
            _scenario_styled_yaml_minimal_diff,
        ),
        (
            "toml_valid_open_71d29a80",
            _scenario_toml_valid_open_71d29a80,
        ),
        (
            "extensionless_open_91b8ce0b",
            _scenario_extensionless_open_91b8ce0b,
        ),
        (
            "created_draft_trailing_newline_62759f8a",
            _scenario_created_draft_trailing_newline_62759f8a,
        ),
        (
            "create_draft_discard_close_2e44a0a9",
            _scenario_create_draft_discard_close_2e44a0a9,
        ),
        (
            "py_replace_functiondef_no_nesting_831a82be",
            _scenario_py_replace_functiondef_no_nesting_831a82be,
        ),
        (
            "py_replace_keeps_leading_comments_5495f4be",
            _scenario_py_replace_keeps_leading_comments_5495f4be,
        ),
        (
            "search_ids_unique_086a8f6c",
            _scenario_search_ids_unique_086a8f6c,
        ),
        (
            "search_stable_id_usable_in_edit_1db1038b",
            _scenario_search_stable_id_usable_in_edit_1db1038b,
        ),
        (
            "yaml_trailing_doc_comment_20b4ba84",
            _scenario_yaml_trailing_doc_comment_20b4ba84,
        ),
    ]


def available_checks() -> list[str]:
    return [METADATA_CHECK_NAME, *[name for name, _fn in _scenario_registry()]]


def _resolve_requested_checks(args: argparse.Namespace) -> list[str]:
    requested = [str(name).strip() for name in getattr(args, "checks", []) if str(name).strip()]
    if not requested:
        return available_checks()
    known = set(available_checks())
    unknown = [name for name in requested if name not in known]
    if unknown:
        raise PipelineFailure(
            "Unknown pipeline checks requested",
            {"unknown": unknown, "available": available_checks()},
        )
    return requested


async def _assert_server_reachable(
    server_name: str, host: str, port: int, *, timeout_seconds: float = 3.0
) -> None:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise PipelineFailure(
            f"{server_name} unreachable at {host}:{port}",
            {
                "server": server_name,
                "host": host,
                "port": port,
                "transport_error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    else:
        del reader
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    ca = _annotate_client(
        _client(args.ca_host, args.ca_port, args.mtls_dir),
        server_name="code-analysis-server",
        host=args.ca_host,
        port=args.ca_port,
    )
    ed = _annotate_client(
        _client(args.editor_host, args.editor_port, args.mtls_dir),
        server_name="ai-editor-server",
        host=args.editor_host,
        port=args.editor_port,
    )
    requested_checks = _resolve_requested_checks(args)
    _progress(
        "Resolved checks: " + ", ".join(requested_checks)
    )
    requires_ca = any(name != METADATA_CHECK_NAME for name in requested_checks)
    await _assert_server_reachable(
        "ai-editor-server", args.editor_host, args.editor_port
    )
    if requires_ca:
        await _assert_server_reachable(
            "code-analysis-server", args.ca_host, args.ca_port
        )

    watch_dir_source = "override"
    watch_dir_id = args.watch_dir_id
    requires_watch_dir = requires_ca
    if requires_watch_dir and not watch_dir_id:
        _progress("Discovering CA watch_dir_id")
        discovered = await _discover_watch_dir_id(ca)
        watch_dir_id = discovered["watch_dir_id"]
        watch_dir_source = discovered["source"]
        _progress(f"Using watch_dir_id={watch_dir_id} from {watch_dir_source}")

    scenarios: list[dict[str, Any]] = []
    if METADATA_CHECK_NAME in requested_checks:
        metadata = await _run_scenario(
            METADATA_CHECK_NAME,
            lambda _ca, _ed, _args, _watch_dir_id: (
                _assert_universal_file_edit_same_process_metadata(_ed)
            ),
            ca,
            ed,
            args,
            watch_dir_id,
        )
        scenarios.append(metadata)

    scenario_map = dict(_scenario_registry())
    for name in requested_checks:
        if name == METADATA_CHECK_NAME:
            continue
        scenarios.append(await _run_scenario(name, scenario_map[name], ca, ed, args, watch_dir_id))

    failed = [scenario for scenario in scenarios if scenario["status"] != "passed"]
    return {
        "pipeline": "verify_editor_ca_chain",
        "transport": "direct_jsonrpc",
        "servers": {
            "ca": {"host": args.ca_host, "port": args.ca_port},
            "editor": {"host": args.editor_host, "port": args.editor_port},
        },
        "watch_dir": {
            "id": watch_dir_id,
            "source": watch_dir_source,
            "required": requires_watch_dir,
        },
        "requested_checks": requested_checks,
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
            ),
            "84d93cca": (
                "open_queue_autopoll reuses the live ai-editor project (not a "
                "throwaway fixture) to reproduce the CAS list_project_files "
                "sync-cap queued handoff at this project's on-disk scale. On the "
                "current degraded casmgr the observed open wall time is ~2 "
                "minutes; this is a KNOWN-DEGRADED, currently-acceptable "
                "duration, logged via open_wall_seconds in the scenario evidence "
                "rather than asserted against a tight bound."
            ),
            "b215fbd3": (
                "styled_yaml_minimal_diff tolerates ONLY the documented flow-map "
                "interior padding normalization ('{ a: 1, b: 2 }' -> "
                "'{a: 1, b: 2}'); any other line change beyond the mutated "
                "scalar fails the scenario."
            ),
            "own_command_coverage": (
                "full own-command coverage: info/search/node_at_line added "
                "2026-07-24. info_guide_smoke exercises 'info' standalone "
                "(no CA context). 86288c9c_python_header_comment_preservation "
                "piggybacks universal_file_search (simple ClassDef/name query, "
                "must match the class node_ref located via preview's block "
                "list) and universal_file_node_at_line (class header line, "
                "include_ancestors=true) on its existing open session; "
                "node_at_line resolves the line's MOST SPECIFIC node (a "
                "nested Name token), so the check asserts the class node_ref "
                "appears among its ancestors rather than as the top-level "
                "result."
            ),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-server AI Editor -> CA acceptance pipeline"
    )
    parser.add_argument(
        "checks",
        nargs="*",
        help=(
            "Optional pipeline check names. With no positional checks, runs the full "
            "suite. Use --list to enumerate names."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available pipeline check names and exit.",
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
        default=Path(_env("AI_EDITOR_MTLS_DIR", str(_default_mtls_dir()))),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.list:
        print("\n".join(available_checks()))
        return 0
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
