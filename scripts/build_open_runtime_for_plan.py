#!/usr/bin/env python3
"""Build open_command_runtime.py (+ optional draft helper split) for plan AS."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "ai_editor/commands/universal_file_edit/open_command.py").read_text()
LINES = SRC.splitlines()


def module_fn(name: str) -> str:
    start = next(i for i, l in enumerate(LINES) if l.startswith(f"def {name}("))
    end = next(i for i, l in enumerate(LINES[start + 1 :], start + 1) if l.startswith("class "))
    return "\n".join(LINES[start:end]).rstrip() + "\n"


def class_method(name: str) -> list[str]:
    start = next(i for i, l in enumerate(LINES) if re.match(rf"    (async )?def {name}\(", l))
    end = next(
        (i for i, l in enumerate(LINES[start + 1 :], start + 1) if re.match(r"    def ", l)),
        len(LINES),
    )
    return LINES[start:end]


def dedent_method(lines: list[str], fname: str, *, async_fn: bool = False) -> str:
    first = lines[0].strip()
    if fname == "run_open_execute":
        head = (
            f"{'async ' if async_fn else ''}def {fname}(\n"
            "    command: Any,\n"
            "    *,\n"
            "    project_id: str,\n"
            "    file_path: str,\n"
            "    create: bool = False,\n"
            "    initial_content: str = \"\",\n"
            "    session_id: str = \"\",\n"
            "    **kwargs: Any,\n"
            ") -> Union[SuccessResult, ErrorResult]:"
        )
    else:
        sig_tail = first.split("(", 1)[1]
        sig_tail = sig_tail.replace("self, ", "").replace("self,", "")
        head = f"def {fname}(command: Any, {sig_tail}"

    body_lines = lines[1:]
    # skip original signature continuation
    while body_lines and body_lines[0].strip().startswith(
        ("self,", "project_id:", "file_path:", "create:", "initial_", "session_id:", "**kwargs", ") ->")
    ):
        body_lines.pop(0)
    # skip docstring block
    if body_lines and body_lines[0].strip().startswith('"""'):
        if body_lines[0].strip().count('"""') >= 2:
            body_lines.pop(0)
        else:
            body_lines.pop(0)
            while body_lines and not body_lines[0].strip().endswith('"""'):
                body_lines.pop(0)
            if body_lines:
                body_lines.pop(0)

    body = [ln.replace("self.", "command.") for ln in body_lines]
    # normalize method body indent (8 spaces -> 4)
    fixed: list[str] = []
    for ln in body:
        if ln.startswith("        "):
            fixed.append("    " + ln[8:])
        else:
            fixed.append(ln)
    body_text = "\n".join(fixed)
    body_text = body_text.replace(
        "command._resolve_and_create_draft(",
        "resolve_and_create_draft(",
    )
    body_text = body_text.replace(
        "command._cleanup_stale(",
        "_cleanup_stale(command, ",
    )
    body_text = body_text.replace(
        "command._resolve_abs_path(",
        "_resolve_abs_path(command, ",
    )
    body_text = body_text.replace(
        "command._create_initial_backup(",
        "_create_initial_backup(command, ",
    )
    return head + "\n" + body_text + "\n"


HEADER = '''\
"""Runtime orchestration for universal_file_open (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    SESSION_NOT_FOUND,
    UNKNOWN_FORMAT,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    check_lock,
    delete_lockfile,
    draft_path_for,
    lockfile_path_for,
    resolve_format_group,
    write_lockfile_pid,
)
from ai_editor.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
    open_fallback_warning,
)
from ai_editor.commands.universal_file_edit.session import (
    apply_source_mutation,
    create_session,
)
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    serialize_tree_temp_roots,
)
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    acquire_tree_temp_for_open,
)

'''


def build_runtime() -> str:
    parts = [HEADER, module_fn("_fix_yaml_string_values"), "\n"]
    parts.append(dedent_method(class_method("execute"), "run_open_execute", async_fn=True))
    for meth in ("_resolve_abs_path", "_cleanup_stale", "_create_initial_backup"):
        parts.append("\n" + dedent_method(class_method(meth), meth))
    parts.append("\nfrom .open_command_draft import resolve_and_create_draft\n")
    return "".join(parts)


def build_draft() -> str:
    header = '''\
"""Draft acquisition helpers for universal_file_open (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import PARSE_ERROR, UNKNOWN_FORMAT, make_error
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    draft_path_for,
    lockfile_path_for,
    resolve_format_group,
)
from ai_editor.commands.universal_file_edit.tree_temp_open_support import acquire_tree_temp_for_open

'''
    parts = [header]
    parts.append(
        dedent_method(class_method("_resolve_and_create_draft"), "resolve_and_create_draft").replace(
            "def resolve_and_create_draft(command: Any, self,", "def resolve_and_create_draft("
        )
    )
    for meth, pub in (
        ("_text_fallback_descriptor", "text_fallback_descriptor"),
        ("_write_draft", "write_draft"),
        ("_write_sidecar_draft", "write_sidecar_draft"),
        ("_write_tree_temp_draft", "write_tree_temp_draft"),
    ):
        code = dedent_method(class_method(meth), pub)
        code = code.replace(f"def {pub}(command: Any, self,", f"def {pub}(command: Any, ")
        code = code.replace("write_draft(command, abs_path", "write_draft(command, abs_path")
        parts.append("\n" + code)
    # fix internal calls in resolve_and_create_draft
    text = "".join(parts)
    text = text.replace("command._write_draft", "write_draft")
    text = text.replace("command._write_sidecar_draft", "write_sidecar_draft")
    text = text.replace("command._write_tree_temp_draft", "write_tree_temp_draft")
    text = text.replace("command._text_fallback_descriptor", "text_fallback_descriptor")
    text = text.replace("write_draft(abs_path", "write_draft(command, abs_path")
    text = text.replace("text_fallback_descriptor(\n        abs_path", "text_fallback_descriptor(command, abs_path")
    text = text.replace("write_sidecar_draft(command, abs_path", "write_sidecar_draft(command, abs_path")
    text = text.replace("write_tree_temp_draft(abs_path", "write_tree_temp_draft(command, abs_path")
    # fix resolve_and_create_draft signature
    text = text.replace("def resolve_and_create_draft(command: Any, \n", "def resolve_and_create_draft(\n")
    text = text.replace("def text_fallback_descriptor(command: Any, \n", "def text_fallback_descriptor(\n")
    text = text.replace("def write_draft(command: Any, \n", "def write_draft(\n    command: Any,\n")
    text = text.replace("def write_tree_temp_draft(command: Any, \n", "def write_tree_temp_draft(\n    command: Any,\n")
    return text


if __name__ == "__main__":
    rt = build_runtime()
    dr = build_draft()
    print("runtime", len(rt.splitlines()), "draft", len(dr.splitlines()))
