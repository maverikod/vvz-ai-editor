#!/usr/bin/env python3
"""Apply full create_file prompts to a4-skeleton AS."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from build_open_runtime_for_plan import build_draft, build_runtime
from build_write_preview_runtime_for_plan import (
    build_preview_runtime,
    build_write_runtime,
)
from split_edit_session_for_plan import build_impl, build_mutations, rename_mutations

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "docs/plans/ai-editor-thin-server"

WORKSPACE_LAYOUT = (REPO / "scripts/generate_create_as_prompts.py")  # noqa - inline below

WORKSPACE_LAYOUT_CODE = '''\
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

WORKSPACE_CLEANUP_CODE = '''\
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
    """Drop all command-layer facades for a CA session id."""
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


def py_block(code: str) -> str:
    return f"```py\n{code.rstrip()}\n```"


def wrap(header: str, code: str, footer: str = "") -> str:
    out = f"{header.strip()}\n\n{py_block(code)}"
    if footer.strip():
        out += f"\n\n{footer.strip()}"
    return out + "\n"


def set_prompt(path: Path, prompt: str) -> int:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["prompt"] = prompt
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    m = re.search(r"```py\n(.*?)```", prompt, re.S)
    return len(m.group(1).splitlines()) if m else 0


def main() -> None:
    # workspace_layout
    p = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-001-workspace-layout-helper.yaml"
    n = set_prompt(
        p,
        wrap(
            "Create `ai_editor/core/edit_session/workspace_layout.py` (operation: create_file).",
            WORKSPACE_LAYOUT_CODE,
            "C-008: `{name}-{uuid}/` under file_subtree_dir. C-007: origin_path is sibling in subtree.",
        ),
    )
    print("workspace_layout", n)

    # workspace cleanup
    p = PLAN / "G-007-broken-session-policy/T-004-zombie-workspace-cleanup/atomic_steps/A-001-workspace-session-cleanup-module.yaml"
    n = set_prompt(
        p,
        wrap(
            "Create `ai_editor/core/workspace_session_cleanup.py` (operation: create_file).",
            WORKSPACE_CLEANUP_CODE,
            "C-025: SessionGuard calls cleanup_zombie_ca_session; uses public session.release_session API.",
        ),
    )
    print("workspace_cleanup", n)

    # edit_session mutations + impl
    mut_code = rename_mutations(build_mutations())
    impl_code = build_impl()
    mut_path = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-006-edit-session-mutations.yaml"
    mut_data = yaml.safe_load(mut_path.read_text(encoding="utf-8"))
    mut_data["prompt"] = wrap(
        "Create `ai_editor/core/edit_session/edit_session_mutations.py` (operation: create_file).",
        mut_code,
        "Functions take session as first arg. Imported at bottom of edit_session_impl as _mut.",
    )
    mut_path.write_text(
        yaml.dump(mut_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("edit_session_mutations", len(mut_code.splitlines()))

    impl_path = PLAN / "G-001-workspace-session-directory/T-003-edit-session-root-base/atomic_steps/A-002-split-edit-session-impl.yaml"
    impl_data = yaml.safe_load(impl_path.read_text(encoding="utf-8"))
    impl_data["depends_on"] = ["A-001", "A-006"]
    impl_data["priority"] = 3
    impl_data["prompt"] = wrap(
        "Create `ai_editor/core/edit_session/edit_session_impl.py` (operation: create_file).",
        impl_code,
        "Move body from monolithic edit_session.py; lifecycle delegates to edit_session_mutations.",
    )
    impl_path.write_text(
        yaml.dump(impl_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("edit_session_impl", len(impl_code.splitlines()))

    # open draft + runtime
    draft_path = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-010-open-command-draft.yaml"
    draft_data = {
        "step_id": "A-010",
        "parent_tactical_step": "T-000",
        "name": "open_command draft helpers",
        "target_file": "ai_editor/commands/universal_file_edit/open_command_draft.py",
        "operation": "create_file",
        "priority": 2,
        "depends_on": [],
        "concepts": ["C-016"],
        "prompt": wrap(
            "Create `ai_editor/commands/universal_file_edit/open_command_draft.py` (operation: create_file).",
            build_draft(),
            "Exports resolve_and_create_draft and write_* helpers used by open_command_runtime.",
        ),
        "verification": {
            "type": "import",
            "target": "ai_editor.commands.universal_file_edit.open_command_draft.resolve_and_create_draft",
            "expected": "Callable importable.",
        },
        "status": "draft",
    }
    draft_path.write_text(
        yaml.dump(draft_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("open_command_draft", len(build_draft().splitlines()))

    open_path = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-001-open-command-runtime.yaml"
    open_data = yaml.safe_load(open_path.read_text(encoding="utf-8"))
    open_data["depends_on"] = ["A-010"]
    open_data["priority"] = 3
    open_data["prompt"] = wrap(
        "Create `ai_editor/commands/universal_file_edit/open_command_runtime.py` (operation: create_file).",
        build_runtime(),
        "Export async run_open_execute(command, **kwargs). Facade stays in open_command.py.",
    )
    open_path.write_text(
        yaml.dump(open_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("open_command_runtime", len(build_runtime().splitlines()))

    # write phases + runtime
    wr_code, wp_code = build_write_runtime()
    phases_path = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-011-write-command-phases.yaml"
    phases_data = yaml.safe_load(phases_path.read_text(encoding="utf-8"))
    phases_data["prompt"] = wrap(
        "Create `ai_editor/commands/universal_file_edit/write_command_phases.py` (operation: create_file).",
        wp_code,
        "Module-level phase helpers imported by write_command_runtime as phases.",
    )
    phases_path.write_text(
        yaml.dump(phases_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("write_command_phases", len(wp_code.splitlines()))

    write_path = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-003-write-command-runtime.yaml"
    write_data = yaml.safe_load(write_path.read_text(encoding="utf-8"))
    write_data["depends_on"] = ["A-011"]
    write_data["priority"] = 3
    write_data["prompt"] = wrap(
        "Create `ai_editor/commands/universal_file_edit/write_command_runtime.py` (operation: create_file).",
        wr_code,
        "Export async run_write_execute(command, **kwargs). Facade stays in write_command.py.",
    )
    write_path.write_text(
        yaml.dump(write_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("write_command_runtime", len(wr_code.splitlines()))

    # preview runtime
    pr_code = build_preview_runtime()
    preview_path = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/atomic_steps/A-005-preview-command-runtime.yaml"
    preview_data = yaml.safe_load(preview_path.read_text(encoding="utf-8"))
    preview_data["prompt"] = wrap(
        "Create `ai_editor/commands/universal_file_preview_runtime.py` (operation: create_file).",
        pr_code,
        "Export async run_preview_execute(command, **kwargs). Facade stays in universal_file_preview_command.py.",
    )
    preview_path.write_text(
        yaml.dump(preview_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print("preview_command_runtime", len(pr_code.splitlines()))

    # T-000 README
    t000 = PLAN / "G-007-broken-session-policy/T-000-oversized-command-split/README.yaml"
    t0 = yaml.safe_load(t000.read_text(encoding="utf-8"))
    steps = list(t0.get("atomic_steps") or [])
    if "A-010" not in steps:
        steps.insert(steps.index("A-001") + 1, "A-010")
    if "A-011" not in steps:
        idx = steps.index("A-003")
        steps.insert(idx, "A-011")
    t0["atomic_steps"] = steps
    t000.write_text(
        yaml.dump(t0, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
