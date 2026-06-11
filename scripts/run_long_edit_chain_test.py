#!/usr/bin/env python3
"""
Long universal-file edit chain test (>=2 KiB files, 10+ draft edits, then write).

Uses direct JSON-RPC to the local test ai-editor-server (same commands as MCP
copy 2 on 192.168.254.28). Does not read or write test_data paths on disk directly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from scripts.pipeline.config import PipelineConfig
from scripts.pipeline.mcp_client import MCPClientWrapper, is_available

MIN_BYTES = 2100
PROJECT_ID = "dbd08d2c-4673-4ec6-b4c1-50fe84cc1269"
PREFIX = "long_edit_chain_2026"
EDIT_COUNT = 10


def _pad(base: str, min_size: int = MIN_BYTES) -> str:
    out = base
    n = 0
    while len(out.encode("utf-8")) < min_size:
        out += f"\n# padding-{n} " + ("x" * 48)
        n += 1
    return out


def _py_initial() -> str:
    return _pad(
        '''"""Long edit chain test module (>=2 KiB)."""
from __future__ import annotations

REVISION = 0


def baseline() -> int:
    """Baseline counter."""
    return REVISION
'''
    )


def _md_initial() -> str:
    return _pad(
        """# Long edit chain test

## Baseline

Initial markdown document for universal_file_edit stress test.

"""
    )


def _txt_initial() -> str:
    return _pad("Long edit chain plain text baseline.\n")


def _rst_initial() -> str:
    return _pad(
        """Long edit chain RST
=====================

Baseline section for edit-chain test.

"""
    )


def _adoc_initial() -> str:
    return _pad(
        """= Long edit chain AsciiDoc

== Baseline

Initial asciidoc for edit-chain test.

"""
    )


def _json_initial() -> str:
    obj: Dict[str, Any] = {"revision": 0, "title": "long-edit-chain", "items": []}
    n = 0
    while len(json.dumps(obj, indent=2).encode("utf-8")) < MIN_BYTES:
        obj["items"].append({"id": n, "note": "padding " + ("y" * 40)})
        n += 1
    return json.dumps(obj, indent=2) + "\n"


def _yaml_initial() -> str:
    lines = ["revision: 0", "title: long-edit-chain", "items:"]
    n = 0
    while len("\n".join(lines).encode("utf-8")) < MIN_BYTES:
        lines.append(f"  - id: {n}")
        lines.append(f"    note: padding {'z' * 40}")
        n += 1
    return "\n".join(lines) + "\n"


def _jsonl_initial() -> str:
    lines: List[str] = []
    n = 0
    while len("\n".join(lines).encode("utf-8")) < MIN_BYTES:
        lines.append(json.dumps({"revision": 0, "seq": n, "payload": "p" * 60}))
        n += 1
    return "\n".join(lines) + "\n"


@dataclass
class FormatSpec:
    rel_path: str
    initial_content: Callable[[], str]
    edit_ops: Callable[[int], List[Dict[str, Any]]]


def _text_insert_ops(i: int) -> List[Dict[str, Any]]:
    return [
        {
            "type": "insert",
            "position": "last",
            "content": f"\n# edit-{i}: appended line at revision {i}\n",
        }
    ]


def _json_ops(i: int) -> List[Dict[str, Any]]:
    return [{"type": "replace", "json_pointer": "/revision", "value": i}]


def _yaml_ops(i: int) -> List[Dict[str, Any]]:
    return [{"type": "replace", "json_pointer": "/revision", "value": i}]


def _py_ops(i: int) -> List[Dict[str, Any]]:
    return [
        {
            "type": "insert",
            "parent_node_id": "__root__",
            "position": "last",
            "code_lines": [
                "",
                f"def stub_{i}() -> int:",
                f'    """Edit iteration {i}."""',
                f"    return {i}",
            ],
        }
    ]


FORMATS: List[FormatSpec] = [
    FormatSpec(f"{PREFIX}/sample.py", _py_initial, _py_ops),
    FormatSpec(f"{PREFIX}/sample.md", _md_initial, _text_insert_ops),
    FormatSpec(f"{PREFIX}/sample.txt", _txt_initial, _text_insert_ops),
    FormatSpec(f"{PREFIX}/sample.rst", _rst_initial, _text_insert_ops),
    FormatSpec(f"{PREFIX}/sample.adoc", _adoc_initial, _text_insert_ops),
    FormatSpec(f"{PREFIX}/sample.json", _json_initial, _json_ops),
    FormatSpec(f"{PREFIX}/sample.yaml", _yaml_initial, _yaml_ops),
    FormatSpec(f"{PREFIX}/sample.yml", _yaml_initial, _yaml_ops),
    FormatSpec(f"{PREFIX}/sample.jsonl", _jsonl_initial, _text_insert_ops),
]


def _unwrap(resp: Any) -> Dict[str, Any]:
    if not isinstance(resp, dict):
        raise RuntimeError(f"Unexpected response type: {type(resp)}")
    if resp.get("success") is False:
        raise RuntimeError(json.dumps(resp, ensure_ascii=False)[:2000])
    data = resp.get("data")
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(json.dumps(data, ensure_ascii=False)[:2000])
    if isinstance(data, dict):
        return data
    return resp


def _call(client: MCPClientWrapper, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
    raw = client.call_command(command, params)
    return _unwrap(raw)


def _run_format(client: MCPClientWrapper, spec: FormatSpec) -> Dict[str, Any]:
    initial = spec.initial_content()
    size = len(initial.encode("utf-8"))
    if size < MIN_BYTES:
        raise RuntimeError(f"{spec.rel_path}: initial size {size} < {MIN_BYTES}")

    opened = _call(
        client,
        "universal_file_open",
        {
            "project_id": PROJECT_ID,
            "file_path": spec.rel_path,
            "create": True,
            "initial_content": initial,
        },
    )
    session_id = opened.get("session_id")
    if not session_id:
        raise RuntimeError(f"open missing session_id: {opened}")

    _call(
        client,
        "universal_file_preview",
        {
            "project_id": PROJECT_ID,
            "session_id": session_id,
            "file_path": spec.rel_path,
        },
    )

    for i in range(1, EDIT_COUNT + 1):
        edited = _call(
            client,
            "universal_file_edit",
            {
                "project_id": PROJECT_ID,
                "session_id": session_id,
                "operations": spec.edit_ops(i),
            },
        )
        if not edited.get("success", True):
            raise RuntimeError(f"edit {i} failed: {edited}")

    is_py = spec.rel_path.endswith(".py")
    if is_py:
        preview = _call(
            client,
            "universal_file_write",
            {"project_id": PROJECT_ID, "session_id": session_id},
        )
        committed = _call(
            client,
            "universal_file_write",
            {"project_id": PROJECT_ID, "session_id": session_id},
        )
    else:
        preview = _call(
            client,
            "universal_file_write",
            {
                "project_id": PROJECT_ID,
                "session_id": session_id,
                "write_mode": "preview",
            },
        )
        committed = _call(
            client,
            "universal_file_write",
            {
                "project_id": PROJECT_ID,
                "session_id": session_id,
                "write_mode": "commit",
            },
        )

    closed = _call(
        client,
        "universal_file_close",
        {"project_id": PROJECT_ID, "session_id": session_id},
    )

    return {
        "file_path": spec.rel_path,
        "initial_bytes": size,
        "edits": EDIT_COUNT,
        "write_preview_phase": preview.get("phase"),
        "write_commit_phase": committed.get("phase"),
        "closed": closed.get("success", True),
    }


def main() -> int:
    if not is_available():
        print("MCP JsonRpcClient unavailable", file=sys.stderr)
        return 1

    client = MCPClientWrapper(
        PipelineConfig(server_host="127.0.0.1", server_port=15000, timeout=300)
    )

    results: List[Dict[str, Any]] = []
    failures: List[str] = []

    for spec in FORMATS:
        try:
            results.append(_run_format(client, spec))
            print(f"OK  {spec.rel_path}", flush=True)
        except Exception as exc:
            failures.append(f"{spec.rel_path}: {exc}")
            print(f"FAIL {spec.rel_path}: {exc}", flush=True)

    summary = {
        "project_id": PROJECT_ID,
        "formats_total": len(FORMATS),
        "ok": len(results),
        "failed": len(failures),
        "results": results,
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
