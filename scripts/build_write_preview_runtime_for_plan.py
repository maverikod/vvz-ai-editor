#!/usr/bin/env python3
"""Extract write/preview command runtime modules for plan AS prompts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]


def class_methods(lines: list[str]) -> list[tuple[str, int, int]]:
    """Return (name, start, end) for each indented def/async def on class."""
    out: list[tuple[str, int, int]] = []
    starts: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        m = re.match(r"    (async )?def (\w+)\(", line)
        if m:
            starts.append((m.group(2), i))
    for idx, (name, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        out.append((name, start, end))
    return out


def _signature_end_index(lines: list[str]) -> int:
    """Index of the last line of the def/async def signature (line with ``) ->``)."""
    for i, line in enumerate(lines):
        if re.search(r"\)\s*->", line):
            return i
    return 0


def _strip_leading_docstring(body_lines: list[str]) -> list[str]:
    if not body_lines or not body_lines[0].strip().startswith('"""'):
        return body_lines
    if body_lines[0].strip().count('"""') >= 2:
        return body_lines[1:]
    out = body_lines[1:]
    while out and not out[0].strip().endswith('"""'):
        out.pop(0)
    if out:
        out.pop(0)
    return out


def method_to_function(
    lines: list[str],
    *,
    fname: str | None = None,
    async_fn: bool = False,
    run_sig: str | None = None,
    command_param: bool = True,
) -> str:
    sig_last = _signature_end_index(lines)
    sig_block = lines[: sig_last + 1]
    body_lines = _strip_leading_docstring(lines[sig_last + 1 :])

    if run_sig:
        head = run_sig
    else:
        m = re.search(r"def (\w+)\(", sig_block[0])
        name = fname or (m.group(1) if m else "fn")
        flat = re.sub(r"\s+", " ", " ".join(l.strip() for l in sig_block))
        flat = re.sub(r"^async def \w+\(", f"async def {name}(", flat)
        flat = re.sub(r"^def \w+\(", f"def {name}(", flat)
        flat = flat.replace("(self, ", "(").replace("(self,", "(")
        if command_param and f"def {name}(command:" not in flat:
            flat = flat.replace(f"def {name}(", f"def {name}(command: Any, ", 1)
            flat = flat.replace(f"async def {name}(", f"async def {name}(command: Any, ", 1)
        if async_fn and not flat.startswith("async "):
            flat = "async " + flat
        head = flat

    fixed: list[str] = []
    for ln in body_lines:
        ln = ln.replace("self.", "command.")
        if ln.startswith("        "):
            fixed.append("    " + ln[8:])
        else:
            fixed.append(ln)
    return head + "\n" + "\n".join(fixed) + "\n"


def rewrite_self_calls(text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        text = text.replace(old, new)
    return text


def build_write_runtime() -> tuple[str, str]:
    path = REPO / "ai_editor/commands/universal_file_edit/write_command.py"
    lines = path.read_text(encoding="utf-8").splitlines()
    methods = {n: lines[s:e] for n, s, e in class_methods(lines)}

    phases_header = '''\
"""Write phase helpers for universal_file_write (C-016, C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    FORMAT_INVALID_ON_OPEN,
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    delete_lockfile,
    lockfile_write_preview_ready,
    read_lockfile_pid,
    write_lockfile_pid,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.tree_temp_write_commit import (
    build_tree_temp_preview_text,
    commit_tree_temp_to_disk,
    serialize_tree_temp_session_source,
)
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.cst_tree.node_stable_id import strip_inline_node_id_lines_from_source
from ai_editor.core.cst_tree.tree_builder import get_tree as get_cst_tree
from ai_editor.core.file_handlers.diff_support import unified_diff_text
from ai_editor.core.git_integration import commit_after_write
from ai_editor.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
    restore_session_format_after_recovery,
    try_clear_invalid_after_write,
    validate_invalid_session_for_commit,
)

'''

    phase_names = [
        "_tree_temp_preview",
        "_tree_temp_write_commit",
        "_generate_code",
        "_text_preview",
        "_text_write_commit",
        "_invalid_text_write_commit",
        "_sidecar_preview",
        "_first_call",
        "_second_call",
    ]
    phase_parts = [phases_header]
    pub_map = {
        "_tree_temp_preview": "tree_temp_preview",
        "_tree_temp_write_commit": "tree_temp_write_commit",
        "_generate_code": "generate_code",
        "_text_preview": "text_preview",
        "_text_write_commit": "text_write_commit",
        "_invalid_text_write_commit": "invalid_text_write_commit",
        "_sidecar_preview": "sidecar_preview",
        "_first_call": "first_call",
        "_second_call": "second_call",
    }
    for priv, pub in pub_map.items():
        fn = method_to_function(methods[priv], fname=pub, command_param=False)
        fn = fn.replace("command._generate_code", "generate_code")
        phase_parts.append(fn)

    phases = "".join(phase_parts)
    phases = rewrite_self_calls(
        phases,
        {
            "self._invalid_text_write_commit": "invalid_text_write_commit",
            "self._generate_code": "generate_code",
            "command._invalid_text_write_commit": "invalid_text_write_commit",
            "command._second_call": "second_call",
            "command._first_call": "first_call",
            "command._generate_code": "generate_code",
        },
    )

    runtime_header = '''\
"""Runtime orchestration for universal_file_write (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from typing import Any

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    lockfile_write_preview_ready,
    read_lockfile_pid,
)
from ai_editor.commands.universal_file_edit.session import get_session

from . import write_command_phases as phases

'''

    run_sig = (
        "async def run_write_execute(\n"
        "    command: Any,\n"
        "    *,\n"
        "    project_id: str,\n"
        "    session_id: str,\n"
        "    write_mode: str = \"preview\",\n"
        "    write_mode_explicit: bool = False,\n"
        "    file_path: str = \"\",\n"
        "    **kwargs: Any,\n"
        ") -> SuccessResult | ErrorResult:"
    )
    run_body = method_to_function(
        methods["execute"],
        fname="run_write_execute",
        async_fn=True,
        run_sig=run_sig,
    )
    repl = {
        "command._tree_temp_preview": "phases.tree_temp_preview",
        "command._tree_temp_write_commit": "phases.tree_temp_write_commit",
        "command._text_preview": "phases.text_preview",
        "command._text_write_commit": "phases.text_write_commit",
        "command._sidecar_preview": "phases.sidecar_preview",
        "command._second_call": "phases.second_call",
        "command._first_call": "phases.first_call",
    }
    run_body = rewrite_self_calls(run_body, repl)
    runtime = runtime_header + "\n" + run_body
    return runtime, phases


def build_preview_runtime() -> str:
    path = REPO / "ai_editor/commands/universal_file_preview_command.py"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # module-level chunk before class
    class_line = next(i for i, l in enumerate(lines) if l.startswith("class UniversalFilePreviewCommand"))
    module_chunk = "\n".join(lines[:class_line]).rstrip()
    # fix relative imports to absolute for runtime module location
    module_chunk = module_chunk.replace("from ..core.exceptions", "from ai_editor.core.exceptions")
    module_chunk = module_chunk.replace("from .base_mcp_command", "from ai_editor.commands.base_mcp_command")
    module_chunk = module_chunk.replace("from .preview_config_defaults", "from ai_editor.commands.preview_config_defaults")
    module_chunk = module_chunk.replace("from .universal_file_preview.", "from ai_editor.commands.universal_file_preview.")
    module_chunk = module_chunk.replace(
        "from ai_editor.commands.universal_file_edit.",
        "from ai_editor.commands.universal_file_edit.",
    )
    module_chunk = module_chunk.replace(
        "from ai_editor.commands.preview_command_metadata",
        "from ai_editor.commands.preview_command_metadata",
    )

    methods = {n: lines[s:e] for n, s, e in class_methods(lines)}
    run_sig = (
        "async def run_preview_execute(\n"
        "    command: Any,\n"
        "    **kwargs: Any,\n"
        ") -> SuccessResult | ErrorResult:"
    )
    run_body = method_to_function(
        methods["execute"],
        fname="run_preview_execute",
        async_fn=True,
        run_sig=run_sig,
    )
    run_body = run_body.replace(
        "command._resolve_project_root(kwargs[\"project_id\"])",
        "command._resolve_project_root(kwargs[\"project_id\"])",
    )
    return module_chunk + "\n\n\n" + run_body


if __name__ == "__main__":
    wr, wp = build_write_runtime()
    pr = build_preview_runtime()
    print("write_runtime", len(wr.splitlines()), "write_phases", len(wp.splitlines()), "preview", len(pr.splitlines()))
