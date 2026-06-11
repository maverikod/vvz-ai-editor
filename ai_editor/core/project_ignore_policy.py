"""
Shared ignore rules for watcher traversal, indexing alignment, and project file listing.

Production defaults skip virtualenv trees, VCS, caches, build artifacts, and common
generated files. Paths under ``.venv`` / ``venv`` are not force-included via
``ignore_exceptions`` glob expansion alone; only allowlisted RECORD-resolved
site-packages paths (and optional diagnostic listing flags) may surface them.

**Callers (by symbol)** — config expansion stays in workers / ``venv_path_policy``:

- ``path_is_under_project_local_venv``: ``scanner`` (ignore / merge), ``venv_path_policy``.
- ``is_ignored_project_relative_path`` / ``filter_paths_for_default_project_listing`` /
  ``LISTING_CACHE_DIRECTORY_SEGMENTS``:
  ``commands/ast/list_files`` (default listing); chunking / indexing should align via
  the same relative-path rules where applicable (listing-only ``show_hidden``).
- ``sql_and_absolute_path_eligible_for_default_status_aggregates``:
  ``commands/worker_status_mcp_commands/get_database_status_build`` (SQL fragments).
- ``filter_ignore_exception_py_paths_for_watcher``: ``multi_project_worker_scan``,
  ``multi_project_worker``, ``file_watcher_pkg/base``, ``venv_path_policy``; defensive
  merge filtering in ``scanner.scan_directory`` when ``immediate_project_roots`` is set.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import AbstractSet, Collection, FrozenSet, Optional

# Cache-like directory basenames: omitted from default ``list_project_files`` unless
# ``show_hidden`` (with dot-prefixed dirs, ``ls -a``-style); venv uses separate flags.
LISTING_CACHE_DIRECTORY_SEGMENTS: FrozenSet[str] = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
    }
)

# Directory basenames: never descend in watcher / prune in project walks.
DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES: FrozenSet[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".nox",
        "nox",
        "eggs",
        ".eggs",
        "wheels",
        "htmlcov",
        "ENV",
        "env.bak",
        "venv.bak",
    }
)

# Basenames matched against path segments (POSIX) for ``is_ignored_project_relative_path``.
DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS: FrozenSet[str] = (
    DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES
)

_DEFAULT_IGNORED_FILE_SUFFIXES: FrozenSet[str] = frozenset(
    {".pyc", ".pyo", ".log", ".coverage"}
)

_DEFAULT_IGNORED_FILE_BASENAME_GLOBS: FrozenSet[str] = frozenset({"*.lock"})


def path_is_under_project_local_venv(resolved_path: Path, project_root: Path) -> bool:
    """
    True if ``resolved_path`` lies under ``project_root/.venv`` or ``project_root/venv``.
    """
    try:
        p = resolved_path.resolve()
        root = project_root.resolve()
    except OSError:
        return False
    for name in (".venv", "venv"):
        try:
            anchor = (root / name).resolve()
            p.relative_to(anchor)
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return False


def is_ignored_project_relative_path(
    relative_posix: str,
    *,
    include_venv: bool = False,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
) -> bool:
    """
    Return True when a project-relative POSIX path should be hidden from normal listing.

    Used by ``list_project_files`` and tests. When ``include_venv`` is True, paths
    under a ``.venv`` or ``venv`` segment are not ignored by this helper (caller may
    still restrict to allowlisted RECORD paths). When ``include_venv_ignore_exceptions``
    is True, paths under venv are not ignored here so ``ignore_exceptions`` expansions
    can appear in diagnostic listings. When ``show_hidden`` is True (``ls -a``-style),
    paths under dot-prefixed directory segments (except ``.venv``/``venv``) and under
    :data:`LISTING_CACHE_DIRECTORY_SEGMENTS` are not ignored for those segments.
    """
    rel = (relative_posix or "").strip().replace("\\", "/").strip("/")
    if not rel:
        return False
    parts = [x for x in rel.split("/") if x]
    for seg in parts:
        if seg in DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS:
            if seg in (".venv", "venv") and (
                include_venv or include_venv_ignore_exceptions
            ):
                continue
            if seg in LISTING_CACHE_DIRECTORY_SEGMENTS and show_hidden:
                continue
            if (
                show_hidden
                and seg.startswith(".")
                and seg not in (".venv", "venv")
            ):
                continue
            return True
    base = parts[-1] if parts else ""
    low = base.lower()
    for suf in _DEFAULT_IGNORED_FILE_SUFFIXES:
        if low.endswith(suf):
            return True
    for pat in _DEFAULT_IGNORED_FILE_BASENAME_GLOBS:
        if fnmatch.fnmatch(base, pat):
            return True
    return False


def sql_and_absolute_path_eligible_for_default_status_aggregates(
    path_column: str,
) -> str:
    """
    Portable SQL AND-fragment so aggregates match "normal" project paths.

    ``files.path`` is absolute; this mirrors :func:`is_ignored_project_relative_path`
    for directory basenames in :data:`DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS` by
    requiring a ``/segment/`` boundary (or end/start) so arbitrary substring
    false positives stay unlikely.

    Append to ``WHERE`` clauses that should exclude virtualenvs, VCS trees, caches,
    etc. from ``get_database_status`` needing_* counts and samples.
    """
    parts: list[str] = []
    for seg in sorted(DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS):
        esc = seg.replace("'", "''")
        parts.append(
            "("
            f"{path_column} LIKE '%/{esc}/%' OR {path_column} LIKE '%/{esc}' "
            f"OR {path_column} LIKE '{esc}/%' OR {path_column} = '{esc}'"
            ")"
        )
    inner = " OR ".join(parts)
    return f" AND NOT ({inner}) "


def filter_paths_for_default_project_listing(
    paths: Collection[Path],
    project_root: Path,
    *,
    include_venv: bool,
    include_venv_ignore_exceptions: bool,
    show_hidden: bool = False,
) -> list[Path]:
    """Drop ignored relative paths; used when assembling ``list_project_files`` results."""
    root = project_root.resolve()
    out: list[Path] = []
    for p in paths:
        try:
            rel = p.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        except OSError:
            continue
        if is_ignored_project_relative_path(
            rel,
            include_venv=include_venv,
            include_venv_ignore_exceptions=include_venv_ignore_exceptions,
            show_hidden=show_hidden,
        ):
            continue
        out.append(p)
    return out


def filter_ignore_exception_py_paths_for_watcher(
    paths: AbstractSet[Path],
    project_roots: Collection[Path],
    allowed_venv_py_files: Optional[AbstractSet[Path]],
) -> set[Path]:
    """
    Drop ``ignore_exceptions`` targets that live under a project venv unless allowlisted.

    Watcher merge still indexes allowlisted RECORD ``.py`` under site-packages; broad
    ``ignore_exceptions`` globs under ``.venv`` must not pull entire site-packages trees.
    """
    allowed = allowed_venv_py_files or frozenset()
    roots = [Path(pr).resolve() for pr in project_roots]
    out: set[Path] = set()
    for p in paths:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp in allowed:
            out.add(rp)
            continue
        under_venv = False
        for root in roots:
            if path_is_under_project_local_venv(rp, root):
                under_venv = True
                break
        if under_venv:
            continue
        out.add(rp)
    return out
