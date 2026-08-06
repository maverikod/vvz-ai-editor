"""Recoverable file-transaction primitive for the source/tree file pair (C-012).

Scope (concept C-012, narrowed to exactly the atomic-publication mechanism):
this module owns the low-level machinery that publishes a small, fixed set
of files (in practice, one document's source file and its serialized tree
file) so that a crash at any point leaves the pair recoverable, and a
reader never observes a torn write. It knows nothing about tree schemas,
checksums, edit sessions, or conflict policy -- those belong to the
sibling storage-lifecycle module built on top of this one. Payload bytes
already fully serialized are handed in by the caller; this module never
parses, validates, or serializes tree content of any kind.

Per {p090}: "Storage/integration-slой sohranyaet svyazannuyu paru kak
vosstanavlivaemuyu faylovuyu tranzaktsiyu... Chastichno opublikovannaya
para obnaruzhivaetsya i vosstanavlivaetsya storage-sloyem pri sleduyushchem
otkrytii." In English: the linked pair is published as a recoverable file
transaction, and a partially published pair is detected and recovered by
the storage layer at the next open.

Protocol (per file entry, target path T, deterministic siblings T+".tmp"
and T+".bak"):

  1. Stage: write the new bytes to T+".tmp" and fsync that file's data.
  2. Journal: write a manifest (JSON) listing every entry -- target, temp,
     backup paths and whether T pre-existed -- to a caller-supplied journal
     path, via the same stage-then-rename durability pattern. The journal
     is the single fact that says "a transaction is in flight"; its
     removal is always the last act of any outcome (success, roll-forward,
     or roll-back).
  3. Backup (only for entries where T pre-existed): create T+".bak" as a
     *hard link* to the still-untouched T, so the original bytes remain
     reachable under two names without ever removing T. No copy is needed.
  4. Publish: `os.rename(T+".tmp", T)`, one atomic filesystem operation
     per entry that swaps T's directory entry onto the staged bytes. T is
     never briefly absent, so a reader opening T at any instant sees
     either the fully old bytes or the fully new bytes, never neither.
  5. Finalize: once every entry's publish rename has happened, drop the
     now-unneeded backups and the journal.

Because step 4 is the only step that consumes (removes) the ".tmp" name,
"is T+'.tmp' gone?" is exactly the fact "did this entry finish publishing"
-- the recovery logic below needs no other bookkeeping to tell rolled-
forward entries from not-yet-published ones.

Recovery, run by the caller at the next open (never automatically inside
`publish`, so the two concerns -- doing a transaction, and discovering one
left mid-flight -- stay separable and both idempotent):

  * No journal on disk: no transaction was in flight (or one already fully
    finalized). Only stray ".tmp" files beside the given targets, left by
    an attempt that crashed before the journal was even written, are
    cleaned up.
  * Journal present, every entry's ".tmp" already consumed: the
    transaction reached step 4 for everything but crashed before step 5.
    Roll forward: drop leftover backups and the journal.
  * Journal present, at least one entry not yet published: roll back --
    for any entry that *did* finish (rename its backup back onto the
    target, or delete the target if the entry created a brand-new file
    with no backup), then drop stray ".tmp"/".bak" files and the journal.
    Every target ends up back at its pre-transaction state.

Filesystem failures at any step raise :class:`StorageIOError`, carrying
:attr:`~tree_engine.errors.ErrorCode.STORAGE_IO_ERROR`, the offending path,
and a `phase` tag. This module performs no checksum computation, no
session/conflict bookkeeping, and no tree-schema parsing -- see the
sibling storage-lifecycle step for all of that.

Source-of-truth requirement labels honored here: {p090}.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from tree_engine.errors import ErrorCode

__all__ = [
    "StorageIOError",
    "FileWrite",
    "RecoveryReport",
    "publish",
    "recover",
]

PathLike = Union[str, Path]


class StorageIOError(Exception):
    """A filesystem failure encountered while publishing or recovering a
    file-transaction. ``code`` is always
    :attr:`~tree_engine.errors.ErrorCode.STORAGE_IO_ERROR`; ``phase``
    names the step that failed (e.g. ``"stage_temp"``, ``"fsync_temp"``,
    ``"backup_link"``, ``"publish_rename"``, ``"rollback_restore"``,
    ``"read_journal"``); ``path`` is the file the failing operation acted
    on."""

    def __init__(self, phase: str, path: Path, message: str) -> None:
        self.code = ErrorCode.STORAGE_IO_ERROR
        self.phase = phase
        self.path = path
        super().__init__(f"[{ErrorCode.STORAGE_IO_ERROR.value}] {phase} failed for {path}: {message}")


@dataclass(frozen=True)
class FileWrite:
    """One entry to publish: the exact bytes that should become the
    contents of ``target_path`` once the transaction commits."""

    target_path: Path
    content: bytes


@dataclass(frozen=True)
class RecoveryReport:
    """Outcome of one :func:`recover` call. ``action`` is ``"none"`` (no
    journal found, nothing but possibly stray temp files to clean),
    ``"rolled_forward"`` (a completed transaction was finalized), or
    ``"rolled_back"`` (an incomplete transaction was undone). ``entries``
    lists the target paths the journal covered (empty when ``action`` is
    ``"none"``)."""

    action: str
    journal_present: bool
    entries: Tuple[Path, ...] = field(default_factory=tuple)
    orphan_temp_files_removed: Tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _PlanEntry:
    target: Path
    temp: Path
    backup: Path
    had_target: bool


def _temp_path(target: Path) -> Path:
    return target.with_name(target.name + ".tmp")


def _backup_path(target: Path) -> Path:
    return target.with_name(target.name + ".bak")


def _stage_temp(temp_path: Path, content: bytes) -> None:
    """Write ``content`` to ``temp_path`` and durably sync its data.
    Creation/write failures raise phase ``"stage_temp"``; a failure of the
    sync itself raises phase ``"fsync_temp"``, kept distinct so callers
    (and the contract tests) can tell the two apart."""

    try:
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    except OSError as exc:
        raise StorageIOError("stage_temp", temp_path, str(exc)) from exc
    try:
        try:
            os.write(fd, content)
        except OSError as exc:
            raise StorageIOError("stage_temp", temp_path, str(exc)) from exc
        try:
            os.fsync(fd)
        except OSError as exc:
            raise StorageIOError("fsync_temp", temp_path, str(exc)) from exc
    finally:
        os.close(fd)


def _rename(src: Path, dst: Path, *, phase: str) -> None:
    try:
        os.rename(str(src), str(dst))
    except OSError as exc:
        raise StorageIOError(phase, dst, str(exc)) from exc


def _link(src: Path, dst: Path, *, phase: str) -> None:
    try:
        os.link(str(src), str(dst))
    except OSError as exc:
        raise StorageIOError(phase, dst, str(exc)) from exc


def _unlink(path: Path, *, phase: str) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StorageIOError(phase, path, str(exc)) from exc


def _build_plan(files: Sequence[FileWrite]) -> List[_PlanEntry]:
    plan: List[_PlanEntry] = []
    for fw in files:
        target = Path(fw.target_path)
        plan.append(
            _PlanEntry(
                target=target,
                temp=_temp_path(target),
                backup=_backup_path(target),
                had_target=target.exists(),
            )
        )
    return plan


def _write_journal(journal_path: Path, plan: Sequence[_PlanEntry]) -> None:
    payload = {
        "version": 1,
        "entries": [
            {
                "target": str(e.target),
                "temp": str(e.temp),
                "backup": str(e.backup),
                "had_target": e.had_target,
            }
            for e in plan
        ],
    }
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    journal_tmp = journal_path.with_name(journal_path.name + ".tmp")
    _stage_temp(journal_tmp, data)
    _rename(journal_tmp, journal_path, phase="write_journal")


def _read_journal(journal_path: Path) -> List[_PlanEntry]:
    try:
        raw = journal_path.read_bytes()
    except OSError as exc:
        raise StorageIOError("read_journal", journal_path, str(exc)) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
        return [
            _PlanEntry(
                target=Path(e["target"]),
                temp=Path(e["temp"]),
                backup=Path(e["backup"]),
                had_target=bool(e["had_target"]),
            )
            for e in payload["entries"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise StorageIOError("read_journal", journal_path, f"corrupt journal: {exc}") from exc


def _finalize(plan: Sequence[_PlanEntry], journal_path: Path) -> None:
    """Both renames are already confirmed done for every entry: drop the
    now-unneeded backups, then the journal itself last."""

    for entry in plan:
        if entry.had_target:
            _unlink(entry.backup, phase="finalize_backup")
    _unlink(journal_path, phase="finalize_journal")


def _rollback(plan: Sequence[_PlanEntry], journal_path: Path) -> List[Path]:
    """Undo every entry back to its pre-transaction state and drop stray
    temp files. Returns the temp paths that were found and removed."""

    orphans: List[Path] = []
    for entry in plan:
        published = not entry.temp.exists()
        if published:
            if entry.had_target:
                _rename(entry.backup, entry.target, phase="rollback_restore")
            elif entry.target.exists():
                _unlink(entry.target, phase="rollback_delete_created")
        else:
            if entry.had_target and entry.backup.exists() and not entry.target.exists():
                _rename(entry.backup, entry.target, phase="rollback_restore")
            elif entry.had_target:
                _unlink(entry.backup, phase="rollback_backup")
        if entry.temp.exists():
            _unlink(entry.temp, phase="rollback_temp")
            orphans.append(entry.temp)
    _unlink(journal_path, phase="finalize_journal")
    return orphans


def publish(files: Sequence[FileWrite], journal_path: PathLike) -> None:
    """Publish every entry in ``files`` as one recoverable transaction.

    On success every ``target_path`` holds its new ``content``, and no
    journal, backup, or temp file is left behind. On a filesystem failure
    at any step, :class:`StorageIOError` propagates and the on-disk state
    is left exactly where the failed step left it -- always safe to hand
    to :func:`recover`, which is the only step responsible for cleanup.
    ``publish`` never attempts recovery itself, so the two concerns stay
    separable and both idempotent.
    """

    if not files:
        raise ValueError("publish() requires at least one FileWrite")
    journal = Path(journal_path)
    plan = _build_plan(files)
    if len({e.target for e in plan}) != len(plan):
        raise ValueError("publish() targets must be distinct paths")

    for entry, fw in zip(plan, files):
        _stage_temp(entry.temp, fw.content)

    _write_journal(journal, plan)

    for entry in plan:
        if entry.had_target:
            _unlink(entry.backup, phase="backup_link")  # clear any stale leftover first
            _link(entry.target, entry.backup, phase="backup_link")

    for entry in plan:
        _rename(entry.temp, entry.target, phase="publish_rename")

    _finalize(plan, journal)


def recover(target_paths: Sequence[PathLike], journal_path: PathLike) -> RecoveryReport:
    """Inspect ``journal_path`` and the deterministic temp/backup siblings
    of ``target_paths`` at open time, and restore a fully consistent
    state: forward if every entry's publish rename already happened,
    backward otherwise. Safe and idempotent to call whether or not a
    transaction was actually in flight.
    """

    targets = [Path(p) for p in target_paths]
    journal = Path(journal_path)

    if not journal.exists():
        removed: List[Path] = []
        for target in targets:
            temp = _temp_path(target)
            if temp.exists():
                _unlink(temp, phase="cleanup_temp")
                removed.append(temp)
        return RecoveryReport(action="none", journal_present=False, orphan_temp_files_removed=tuple(removed))

    plan = _read_journal(journal)
    entry_targets = tuple(e.target for e in plan)
    all_published = all(not e.temp.exists() for e in plan)

    if all_published:
        _finalize(plan, journal)
        return RecoveryReport(action="rolled_forward", journal_present=True, entries=entry_targets)

    orphans = _rollback(plan, journal)
    return RecoveryReport(
        action="rolled_back",
        journal_present=True,
        entries=entry_targets,
        orphan_temp_files_removed=tuple(orphans),
    )
