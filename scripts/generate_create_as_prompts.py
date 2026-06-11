#!/usr/bin/env python3
"""Fill a4-skeleton create_file AS with full module bodies."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "docs/plans/ai-editor-thin-server"


def py_block(code: str) -> str:
    return f"```py\n{code.rstrip()}\n```"


def wrap_prompt(header: str, code: str, footer: str = "") -> str:
    parts = [header.strip(), "", py_block(code)]
    if footer.strip():
        parts.extend(["", footer.strip()])
    return "\n".join(parts) + "\n"


WORKSPACE_LAYOUT = '''\
"""Edit subdir allocation inside File Subtree (C-008, C-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoreSessionPaths:
    """Paths for one core EditSession workspace-mode open."""

    origin_path: Path
    edit_subdir: Path
    session_source_path: Path
    session_dir: Path


def allocate_edit_subdir(*, file_subtree_dir: Path, origin_filename: str) -> CoreSessionPaths:
    """Create ``file_subtree_dir/{origin_filename}-{uuid4}/`` (mkdir only).

    Does not copy origin snapshot; caller writes ``origin_path`` separately.
    """
    name = Path(origin_filename).name
    if not name:
        raise ValueError("origin_filename must be non-empty")
    subdir_name = f"{name}-{uuid.uuid4()}"
    edit_subdir = (file_subtree_dir / subdir_name).resolve()
    edit_subdir.mkdir(parents=True, exist_ok=False)
    origin_path = file_subtree_dir / name
    session_source_path = edit_subdir / name
    return CoreSessionPaths(
        origin_path=origin_path,
        edit_subdir=edit_subdir,
        session_source_path=session_source_path,
        session_dir=edit_subdir,
    )
'''

WORKSPACE_CLEANUP = '''\
"""Zombie CA session workspace cleanup (C-025).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _purge_bundle(ca_session_id: str) -> None:
    """Drop all command-layer facades for a CA session id (public release_session API)."""
    from ai_editor.commands.universal_file_edit.session import get_session, release_session

    while True:
        try:
            session = get_session(ca_session_id)
        except ValueError:
            break
        release_session(ca_session_id, session.file_path)


def cleanup_zombie_ca_session(
    ca_session_id: str,
    *,
    workspace_root: Path,
) -> bool:
    """Remove ``{workspace_root}/{ca_session_id}/`` and in-memory bundle (C-025)."""
    sid = str(ca_session_id or "").strip()
    if not sid:
        return False
    root = workspace_root.resolve()
    session_dir = (root / sid).resolve()
    try:
        session_dir.relative_to(root)
    except ValueError:
        logger.warning("cleanup path outside workspace: %s", session_dir)
        return False
    _purge_bundle(sid)
    if session_dir.is_dir():
        shutil.rmtree(session_dir)
    return True
'''


def build_open_command_runtime() -> str:
    src = (REPO / "ai_editor/commands/universal_file_edit/open_command.py").read_text()
    lines = src.splitlines()
    # Module helpers before class + class methods (exclude class shell attrs/schema/metadata)
    start = next(i for i, l in enumerate(lines) if l.startswith("def _fix_yaml"))
    class_start = next(i for i, l in enumerate(lines) if l.startswith("class UniversalFileOpenCommand"))
    execute_start = next(
        i for i, l in enumerate(lines) if l.strip().startswith("async def execute")
    )
    execute_end = next(
        i
        for i, l in enumerate(lines[execute_start:], execute_start)
        if l.startswith("    def _resolve_abs_path")
    )
    helper_start = execute_end
    helper_end = len(lines)
    while helper_end > helper_start and not lines[helper_end - 1].strip():
        helper_end -= 1

    pre_class = "\n".join(lines[start:class_start]).rstrip()
    execute_body = "\n".join(lines[execute_start + 1 : execute_end]).rstrip()
    helpers = "\n".join(lines[helper_start:helper_end]).rstrip()
    # dedent execute body from 8 spaces to 4
    execute_body = textwrap.dedent(execute_body)

    header = '''\
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

    run_open = f'''
async def run_open_execute(
    command: Any,
    *,
    project_id: str,
    file_path: str,
    create: bool = False,
    initial_content: str = "",
    session_id: str = "",
    **kwargs: Any,
) -> Union[SuccessResult, ErrorResult]:
    """Execute open orchestration (extracted from UniversalFileOpenCommand.execute)."""
{textwrap.indent(execute_body, "    ")}
'''

    helpers_dedented = textwrap.dedent(
        helpers.replace("    def _", "\ndef _").replace("    async def ", "\nasync def ")
    )
    helpers_dedented = re.sub(r"^self\.", "command.", helpers_dedented, flags=re.M)
    helpers_dedented = helpers_dedented.replace("self._", "command._")

    return header + "\n" + pre_class + run_open + "\n\n" + helpers_dedented + "\n"


def build_edit_session_impl() -> tuple[str, str]:
    src = (REPO / "ai_editor/core/edit_session/edit_session.py").read_text()
    lines = src.splitlines()
    # Split at checkout_history_index
    split_at = next(i for i, l in enumerate(lines) if "def checkout_history_index" in l)
    head = "\n".join(lines[:split_at]).rstrip()
    tail = "\n".join(lines[split_at:]).rstrip()
    # Remove get_active_session from tail
    tail = tail.split("def get_active_session")[0].rstrip()

    mutations_header = '''\
"""EditSession lifecycle helpers (checkout, undo, external copy).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import os
import shutil
from typing import TYPE_CHECKING, Any

from ai_editor.core.edit_session.marker_cycle import (
    denude_marked_tree,
    restore_marked_tree,
)
from ai_editor.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    NodeIdMap,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from ai_editor.core.tree_lifecycle import compute_content_checksum, is_tree_valid
from ai_editor.tree.handler_registry import HandlerRegistry

if TYPE_CHECKING:
    from .edit_session_impl import EditSession, SessionTreeValidity

'''

    # Convert methods to functions taking session as first arg
    mut_lines: list[str] = []
    for line in tail.splitlines():
        if line.startswith("    def "):
            mut_lines.append(line.replace("    def ", "def ", 1))
        elif line.startswith("        ") or line.strip() == "":
            mut_lines.append(line)
        else:
            mut_lines.append(line)
    mut_body = "\n".join(mut_lines)
    mut_body = mut_body.replace("self.", "session.")
    mut_body = mut_body.replace("SessionTreeValidity", "session.SessionTreeValidity")
    # fix enum refs
    mut_body = mut_body.replace(
        "session.SessionTreeValidity.VALID",
        "SessionTreeValidity.VALID",
    )
    mut_body = mut_body.replace(
        "session.SessionTreeValidity.INVALID",
        "SessionTreeValidity.INVALID",
    )

    mutations_import = (
        "from .edit_session_impl import SessionTreeValidity, _active_sessions\n\n"
    )
    mutations_code = mutations_header + mutations_import + mut_body

    impl_header = head.replace(
        "class EditSession:",
        "from . import edit_session_mutations as _mut\n\n\nclass EditSession:",
    )
    # Bind methods at end of impl file
    bind = '''

def _bind_lifecycle_methods() -> None:
    EditSession.checkout_history_index = _mut.checkout_history_index  # type: ignore[method-assign]
    EditSession.undo = _mut.undo  # type: ignore[method-assign]
    EditSession.redo = _mut.redo  # type: ignore[method-assign]
    EditSession.record_revert_commit = _mut.record_revert_commit  # type: ignore[method-assign]
    EditSession.preview_external_write = _mut.preview_external_write  # type: ignore[method-assign]
    EditSession.confirm_external_copy_out = _mut.confirm_external_copy_out  # type: ignore[method-assign]
    EditSession.close = _mut.close  # type: ignore[method-assign]
    EditSession.record_tree_modification = _mut.record_tree_modification  # type: ignore[method-assign]


_bind_lifecycle_methods()
'''
    # Simpler: keep methods on class in impl - use mixin import at class definition

    # Re-read: use simpler split - impl has full class, mutations as separate file with functions
    # For impl, keep head + stub methods delegating to _mut

    delegate_methods = '''
    def checkout_history_index(self, index: int) -> None:
        _mut.checkout_history_index(self, index)

    def undo(self) -> dict[str, object]:
        return _mut.undo(self)

    def redo(self) -> dict[str, object]:
        return _mut.redo(self)

    def record_revert_commit(self, *, rev: str) -> str:
        return _mut.record_revert_commit(self, rev=rev)

    def preview_external_write(self) -> dict[str, Any]:
        return _mut.preview_external_write(self)

    def confirm_external_copy_out(self) -> None:
        _mut.confirm_external_copy_out(self)

    def close(self) -> None:
        _mut.close(self)

    def record_tree_modification(self) -> None:
        _mut.record_tree_modification(self)
'''
    impl_code = impl_header + delegate_methods + "\n"
    return impl_code, mutations_header + mut_body


def update_yaml(path: Path, prompt: str) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["prompt"] = prompt
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    n = len(re.search(r"```(?:py|python)\n(.*?)```", prompt, re.S).group(1).splitlines())
    print(f"  {path.name}: {n} lines in py block")


def main() -> None:
    # 1 workspace_layout
    p1 = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-001-workspace-layout-helper.yaml"
    update_yaml(
        p1,
        wrap_prompt(
            "Create `ai_editor/core/edit_session/workspace_layout.py` (operation: create_file).",
            WORKSPACE_LAYOUT,
            "C-008: edit subdir `{name}-{uuid}/` under file_subtree_dir. C-007: origin_path sibling in subtree.",
        ),
    )

    # 2 workspace cleanup
    p2 = PLAN / "G-007-broken-session-policy/T-004-zombie-workspace-cleanup/atomic_steps/A-001-workspace-session-cleanup-module.yaml"
    update_yaml(
        p2,
        wrap_prompt(
            "Create `ai_editor/core/workspace_session_cleanup.py` (operation: create_file).",
            WORKSPACE_CLEANUP,
            "C-025: SessionGuard calls cleanup_zombie_ca_session; no direct bundle registry import.",
        ),
    )

    # 3 edit_session split
    impl, mutations = build_edit_session_impl()
    print(f"  edit_session_impl draft: {len(impl.splitlines())} lines")
    print(f"  edit_session_mutations draft: {len(mutations.splitlines())} lines")

    mut_path = (
        PLAN
        / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-006-edit-session-mutations.yaml"
    )
    mut_data = {
        "step_id": "A-006",
        "parent_tactical_step": "T-003",
        "name": "EditSession lifecycle mutations",
        "target_file": "ai_editor/core/edit_session/edit_session_mutations.py",
        "operation": "create_file",
        "priority": 2,
        "depends_on": ["A-001"],
        "concepts": ["C-019"],
        "prompt": wrap_prompt(
            "Create `ai_editor/core/edit_session/edit_session_mutations.py` (operation: create_file).",
            mutations,
            "Module functions take `session: EditSession` as first parameter. Imported by edit_session_impl.",
        ),
        "verification": {
            "type": "import",
            "target": "ai_editor.core.edit_session.edit_session_mutations.checkout_history_index",
            "expected": "Callable importable.",
        },
        "status": "draft",
    }
    mut_path.write_text(
        yaml.dump(mut_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"  wrote {mut_path.name}")

    p_impl = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-002-split-edit-session-impl.yaml"
    impl_data = yaml.safe_load(p_impl.read_text(encoding="utf-8"))
    impl_data["depends_on"] = ["A-001", "A-006"]
    impl_data["priority"] = 3
    impl_data["prompt"] = wrap_prompt(
        "Create `ai_editor/core/edit_session/edit_session_impl.py` (operation: create_file).",
        impl,
        "Move implementation from monolithic edit_session.py. Facade methods delegate to edit_session_mutations.",
    )
    p_impl.write_text(
        yaml.dump(impl_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    update_yaml(p_impl, impl_data["prompt"])

    # Renumber priorities in T-003
    renames = {
        "A-005-delete-edit-session-monolith.yaml": 4,
        "A-003-recreate-edit-session-facade.yaml": 5,
        "A-004-edit-session-open-workspace-mode.yaml": 6,
    }
    as_dir = p_impl.parent
    for fname, pri in renames.items():
        fp = as_dir / fname
        d = yaml.safe_load(fp.read_text(encoding="utf-8"))
        d["priority"] = pri
        fp.write_text(
            yaml.dump(d, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )

    # Update T-003 README
    readme = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/README.yaml"
    rd = yaml.safe_load(readme.read_text(encoding="utf-8"))
    rd["atomic_steps"] = ["A-001", "A-006", "A-002", "A-005", "A-003", "A-004"]
    readme.write_text(
        yaml.dump(rd, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    # 4 open_command_runtime - manual refined build
    runtime = build_open_command_runtime()
    print(f"  open_command_runtime draft: {len(runtime.splitlines())} lines")
    p_open = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-001-open-command-runtime.yaml"
    update_yaml(
        p_open,
        wrap_prompt(
            "Create `ai_editor/commands/universal_file_edit/open_command_runtime.py` (operation: create_file).",
            runtime,
            "Export `run_open_execute` and module helpers. UniversalFileOpenCommand facade stays in open_command.py.",
        ),
    )


if __name__ == "__main__":
    main()
