"""
Shared helpers for file mutations: cooperative locks and documentation hooks.

**Policy:** mutating commands should (1) take :func:`file_lock_many` on all affected
paths (sorted, de-duplicated), (2) create a :class:`~ai_editor.core.backup_manager.BackupManager`
snapshot before overwriting or removing existing files, and (3) call
:func:`ai_editor.core.git_integration.commit_after_write` when
``ai_editor.git_commit_on_write`` is enabled.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from contextlib import contextmanager
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence

from .file_lock import file_lock


@contextmanager
def file_lock_many(
    paths: Sequence[Path],
    *,
    mode: str = "full",
    shared: bool = False,
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    database: Any = None,
    project_id: Optional[str] = None,
    file_paths: Optional[Sequence[str]] = None,
    session_id: Optional[str] = None,
) -> Iterator[None]:
    """Hold :func:`file_lock` on each distinct path, in stable sorted order.

    Avoids deadlocks when two commands use the same global ordering.
    """
    seen: set[str] = set()
    ordered: List[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    ordered.sort(key=lambda x: str(x.resolve()))
    rel_by_path: dict[str, str] = {}
    if file_paths is not None:
        for abs_path, rel_path in zip(paths, file_paths):
            rel_by_path[str(abs_path.resolve())] = rel_path
    with ExitStack() as stack:
        for p in ordered:
            stack.enter_context(
                file_lock(
                    p,
                    mode=mode,
                    shared=shared,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    database=database,
                    project_id=project_id,
                    file_path=rel_by_path.get(str(p.resolve())),
                    session_id=session_id,
                )
            )
        yield
