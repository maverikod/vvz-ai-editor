#!/usr/bin/env python3
"""Live-server smoke: session_undo / session_redo on all universal_file formats."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

_REPO = Path(__file__).resolve().parents[1]
_CLIENT = _REPO / "client"
_EXAMPLES = _CLIENT / "examples"
for p in (_CLIENT, _EXAMPLES):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from _common import chdir_repo_root, default_config_path, ensure_client_package_on_path  # noqa: E402

ensure_client_package_on_path()
chdir_repo_root()

from ai_editor_client import CodeAnalysisAsyncClient  # noqa: E402

import uuid

PROJECT_ID = "b09406a6-2392-4c1e-ba8f-1a74536b83e2"
PREFIX = f"undo_smoke_live_{uuid.uuid4().hex[:8]}"


def _inner(resp: dict[str, Any]) -> dict[str, Any]:
    if resp.get("success") is not True:
        raise RuntimeError(resp)
    data = resp.get("data")
    return data if isinstance(data, dict) else resp


async def _close(client: CodeAnalysisAsyncClient, session_id: str) -> None:
    await client.call(
        "universal_file_close",
        {"project_id": PROJECT_ID, "session_id": session_id},
    )


async def _flow(
    client: CodeAnalysisAsyncClient,
    label: str,
    file_path: str,
    *,
    create: bool,
    initial_content: str,
    edits: list[list[dict[str, Any]]],
    branch_edit: list[dict[str, Any]],
    read_value: Callable[[str], Any],
    expected: list[Any],
    branch_expected: Any,
    resolve_edits: Callable[
        [str],
        Awaitable[tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]],
    ]
    | None = None,
) -> None:
    open_params: dict[str, Any] = {
        "project_id": PROJECT_ID,
        "file_path": file_path,
    }
    if create:
        open_params["create"] = True
        open_params["initial_content"] = initial_content
    opened = _inner(await client.call("universal_file_open", open_params))
    session_id = str(opened["session_id"])
    if resolve_edits is not None:
        edit_batches, branch_edit = await resolve_edits(session_id)

    try:
        for batch in edits:
            _inner(
                await client.call(
                    "universal_file_edit",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": session_id,
                        "operations": batch,
                    },
                )
            )

        preview = _inner(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
        )
        draft_text = str(preview.get("focus", {}).get("text") or "")
        assert read_value(draft_text) == expected[-1], (
            f"{label}: after edits expected {expected[-1]!r}, got {draft_text!r}"
        )

        _inner(
            await client.call(
                "session_undo",
                {"project_id": PROJECT_ID, "session_id": session_id},
            )
        )
        preview = _inner(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
        )
        assert read_value(str(preview["focus"]["text"])) == expected[-2], label

        _inner(
            await client.call(
                "session_undo",
                {"project_id": PROJECT_ID, "session_id": session_id},
            )
        )
        preview = _inner(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
        )
        assert read_value(str(preview["focus"]["text"])) == expected[0], label

        _inner(
            await client.call(
                "session_redo",
                {"project_id": PROJECT_ID, "session_id": session_id},
            )
        )
        preview = _inner(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
        )
        assert read_value(str(preview["focus"]["text"])) == expected[-2], label

        _inner(
            await client.call(
                "universal_file_edit",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "operations": branch_edit,
                },
            )
        )
        preview = _inner(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "session_id": session_id,
                    "file_path": file_path,
                },
            )
        )
        assert read_value(str(preview["focus"]["text"])) == branch_expected, label

        redo_resp = await client.call(
            "session_redo",
            {"project_id": PROJECT_ID, "session_id": session_id},
        )
        assert redo_resp.get("success") is False, redo_resp
        err = redo_resp.get("error") or {}
        code = err.get("code") if isinstance(err, dict) else redo_resp.get("code")
        assert code == "NOTHING_TO_REDO", redo_resp

        print(f"OK  {label}")
    finally:
        await _close(client, session_id)


async def _scalar_ref(
    client: CodeAnalysisAsyncClient, session_id: str, file_path: str, pointer: str
) -> int:
    preview = _inner(
        await client.call(
            "universal_file_preview",
            {
                "project_id": PROJECT_ID,
                "session_id": session_id,
                "file_path": file_path,
            },
        )
    )
    needle = pointer.lstrip("/")
    for block in preview.get("blocks") or []:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if pointer in attrs or f"/{needle}" in attrs or f"'/{needle}'" in attrs:
            return int(block["node_ref"])
        block_attrs = block.get("attributes") or {}
        jp = block_attrs.get("json_pointer") or block_attrs.get("yaml_pointer")
        if jp in {pointer, f"/{needle}", needle}:
            return int(block["node_ref"])
    raise RuntimeError(f"node_ref for {pointer} not found in preview: {preview!r}")


async def main() -> int:
    config = default_config_path()
    async with CodeAnalysisAsyncClient.from_server_config_path(config) as client:
        json_path = f"{PREFIX}/counter.json"
        opened = _inner(
            await client.call(
                "universal_file_open",
                {
                    "project_id": PROJECT_ID,
                    "file_path": json_path,
                    "create": True,
                    "initial_content": '{"counter": 1}\n',
                },
            )
        )
        sid = str(opened["session_id"])
        counter_ref = await _scalar_ref(client, sid, json_path, "/counter")
        await _close(client, sid)

        await _flow(
            client,
            "json",
            json_path,
            create=False,
            initial_content="",
            edits=[
                [{"type": "replace", "node_ref": counter_ref, "value": 2}],
                [{"type": "replace", "node_ref": counter_ref, "value": 3}],
            ],
            branch_edit=[{"type": "replace", "node_ref": counter_ref, "value": 99}],
            read_value=lambda t: json.loads(t)["counter"],
            expected=[1, 2, 3],
            branch_expected=99,
        )

        yaml_path = f"{PREFIX}/counter.yaml"
        await _flow(
            client,
            "yaml",
            yaml_path,
            create=True,
            initial_content="counter: 1\n",
            edits=[
                [{"type": "replace", "json_pointer": "/counter", "value": 2}],
                [{"type": "replace", "json_pointer": "/counter", "value": 3}],
            ],
            branch_edit=[{"type": "replace", "json_pointer": "/counter", "value": 99}],
            read_value=lambda t: int(re.search(r"counter:\s*(\d+)", t).group(1)),
            expected=[1, 2, 3],
            branch_expected=99,
        )

        await _flow(
            client,
            "text",
            f"{PREFIX}/note.txt",
            create=True,
            initial_content="Line one.\nLine two.\nLine three.\n",
            edits=[
                [
                    {
                        "type": "replace",
                        "start_line": 3,
                        "end_line": 3,
                        "content": "Line two edited.\n",
                    }
                ],
                [
                    {
                        "type": "replace",
                        "start_line": 3,
                        "end_line": 3,
                        "content": "Line two final.\n",
                    }
                ],
            ],
            branch_edit=[
                {
                    "type": "replace",
                    "start_line": 3,
                    "end_line": 3,
                    "content": "Line branch.\n",
                }
            ],
            read_value=lambda t: t.splitlines()[2].strip(),
            expected=["Line three.", "Line two edited.", "Line two final."],
            branch_expected="Line branch.",
        )

        await _flow(
            client,
            "markdown",
            f"{PREFIX}/note.md",
            create=True,
            initial_content="# Title\n\nBody one.\n",
            edits=[
                [
                    {
                        "type": "replace",
                        "start_line": 3,
                        "end_line": 3,
                        "content": "Body two.\n",
                    }
                ],
                [
                    {
                        "type": "replace",
                        "start_line": 3,
                        "end_line": 3,
                        "content": "Body three.\n",
                    }
                ],
            ],
            branch_edit=[
                {
                    "type": "replace",
                    "start_line": 3,
                    "end_line": 3,
                    "content": "Body final.\n",
                }
            ],
            read_value=lambda t: re.search(r"Body \w+\.", t).group(0),
            expected=["Body one.", "Body two.", "Body three."],
            branch_expected="Body final.",
        )

        py_path = f"{PREFIX}/module.py"
        open_params = {
            "project_id": PROJECT_ID,
            "file_path": py_path,
            "create": True,
            "initial_content": "def value():\n    return 1\n",
        }
        opened = _inner(await client.call("universal_file_open", open_params))
        py_session = str(opened["session_id"])
        try:
            preview0 = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            fn_stable = str(preview0["focus"]["attributes"]["internal_node_id"])

            async def py_replace(n: int) -> None:
                _inner(
                    await client.call(
                        "universal_file_edit",
                        {
                            "project_id": PROJECT_ID,
                            "session_id": py_session,
                            "operations": [
                                {
                                    "type": "replace",
                                    "node_id": fn_stable,
                                    "code_lines": [
                                        "def value():",
                                        f"    return {n}",
                                    ],
                                }
                            ],
                        },
                    )
                )

            await py_replace(2)
            await py_replace(3)
            preview = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            assert int(re.search(r"return\s+(\d+)", preview["focus"]["text"]).group(1)) == 3

            _inner(
                await client.call(
                    "session_undo",
                    {"project_id": PROJECT_ID, "session_id": py_session},
                )
            )
            preview = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            assert int(re.search(r"return\s+(\d+)", preview["focus"]["text"]).group(1)) == 2

            _inner(
                await client.call(
                    "session_undo",
                    {"project_id": PROJECT_ID, "session_id": py_session},
                )
            )
            preview = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            assert int(re.search(r"return\s+(\d+)", preview["focus"]["text"]).group(1)) == 1

            _inner(
                await client.call(
                    "session_redo",
                    {"project_id": PROJECT_ID, "session_id": py_session},
                )
            )
            preview = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            assert int(re.search(r"return\s+(\d+)", preview["focus"]["text"]).group(1)) == 2

            await py_replace(99)
            preview = _inner(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "session_id": py_session,
                        "file_path": py_path,
                    },
                )
            )
            assert int(re.search(r"return\s+(\d+)", preview["focus"]["text"]).group(1)) == 99

            redo_resp = await client.call(
                "session_redo",
                {"project_id": PROJECT_ID, "session_id": py_session},
            )
            assert redo_resp.get("success") is False
            err = redo_resp.get("error") or {}
            assert (err.get("code") if isinstance(err, dict) else None) == "NOTHING_TO_REDO"

            print("OK  python")
        finally:
            await _close(client, py_session)

    print("ALL FORMATS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
