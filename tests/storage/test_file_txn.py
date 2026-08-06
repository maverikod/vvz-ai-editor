"""Tests for the recoverable file-transaction primitive (C-012, {p090}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.file_txn`` -- ``publish``/``recover`` over the
source/tree file pair's atomic-publication mechanism only. Every scenario
here runs against a real temporary directory with real files, real
``os.rename``/``os.link`` calls, and real crashes reproduced by driving the
module's own private steps (``_stage_temp``, ``_write_journal``, ``_link``,
``_rename``) only partway through the documented protocol and stopping --
never by mocking any filesystem call. The one exception is a background
reader thread used to observe live disk state during a real ``publish()``
call, which is concurrency, not mocking.

Source-of-truth requirement labels honored here: {p090}.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import List

import pytest

from tree_engine.errors import ErrorCode
from tree_engine.storage import file_txn as file_txn_module
from tree_engine.storage.file_txn import FileWrite, RecoveryReport, StorageIOError, publish, recover


def _drive_partial_publish(
    files: List[FileWrite], journal: Path, *, renames_done: int
) -> List["file_txn_module._PlanEntry"]:
    """Replay ``publish()``'s own protocol -- stage, journal, backup, then
    only the first ``renames_done`` publish-renames -- and stop there. This
    is the exact on-disk state a process crash at that point would leave,
    produced with the module's real steps against the real filesystem, not
    a mock standing in for a crash."""

    plan = file_txn_module._build_plan(files)
    for entry, fw in zip(plan, files):
        file_txn_module._stage_temp(entry.temp, fw.content)
    file_txn_module._write_journal(journal, plan)
    for entry in plan:
        if entry.had_target:
            file_txn_module._link(entry.target, entry.backup, phase="backup_link")
    for entry in plan[:renames_done]:
        file_txn_module._rename(entry.temp, entry.target, phase="publish_rename")
    return plan


def _assert_no_residue(*targets: Path) -> None:
    for target in targets:
        assert not file_txn_module._temp_path(target).exists()
        assert not file_txn_module._backup_path(target).exists()


# ---- Happy path -------------------------------------------------------------


def test_valid_publication_no_residue(tmp_path: Path) -> None:
    """A clean multi-file publish leaves every target holding its new
    content and no journal, temp, or backup file behind; a subsequent
    ``recover`` call over the same paths finds nothing left to do."""

    source = tmp_path / "doc.src"
    tree = tmp_path / "doc.tree"
    source.write_bytes(b"old source bytes")
    journal = tmp_path / "doc.journal"

    files = [FileWrite(source, b"new source bytes"), FileWrite(tree, b"new tree bytes")]
    publish(files, journal)

    assert source.read_bytes() == b"new source bytes"
    assert tree.read_bytes() == b"new tree bytes"
    assert not journal.exists()
    _assert_no_residue(source, tree)

    report = recover([source, tree], journal)
    assert report == RecoveryReport(action="none", journal_present=False)


# ---- Crash recovery matrix ---------------------------------------------------


def test_recovery_crash_before_rename(tmp_path: Path) -> None:
    """A crash after the journal is durably written but before any publish
    rename leaves every temp file still present; recovery rolls back to the
    untouched pre-transaction state and truthfully reports doing so."""

    source = tmp_path / "doc.src"
    tree = tmp_path / "doc.tree"
    source.write_bytes(b"old source")
    journal = tmp_path / "doc.journal"
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    plan = _drive_partial_publish(files, journal, renames_done=0)

    report = recover([source, tree], journal)

    assert report.action == "rolled_back"
    assert report.journal_present is True
    assert report.entries == (source, tree)
    assert set(report.orphan_temp_files_removed) == {entry.temp for entry in plan}

    assert source.read_bytes() == b"old source"
    assert not tree.exists()
    assert not journal.exists()
    _assert_no_residue(source, tree)


def test_recovery_crash_between_renames(tmp_path: Path) -> None:
    """A crash after the first entry's publish rename but before the
    second's must not leave a mixed pair: recovery rolls the already
    -renamed entry back too, so both files end up at identical
    pre-transaction bytes -- never old+new mixed, never new+new."""

    source = tmp_path / "doc.src"
    tree = tmp_path / "doc.tree"
    source.write_bytes(b"old source")
    tree.write_bytes(b"old tree")
    journal = tmp_path / "doc.journal"
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    _drive_partial_publish(files, journal, renames_done=1)

    # Mid-crash sanity: the first entry already shows its new bytes, the
    # second is still untouched -- exactly the torn state a crash leaves.
    assert source.read_bytes() == b"new source"
    assert tree.read_bytes() == b"old tree"

    report = recover([source, tree], journal)

    assert report.action == "rolled_back"
    assert report.entries == (source, tree)
    assert source.read_bytes() == b"old source"
    assert tree.read_bytes() == b"old tree"
    assert not journal.exists()
    _assert_no_residue(source, tree)


def test_recovery_rolled_forward_completes_pending_finalize(tmp_path: Path) -> None:
    """A crash after every publish rename succeeded but before finalize
    must roll forward, not back: both targets keep their new bytes, and
    recovery only sweeps the now-unneeded backups and journal."""

    source = tmp_path / "doc.src"
    tree = tmp_path / "doc.tree"
    source.write_bytes(b"old source")
    tree.write_bytes(b"old tree")
    journal = tmp_path / "doc.journal"
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    _drive_partial_publish(files, journal, renames_done=2)

    report = recover([source, tree], journal)

    assert report.action == "rolled_forward"
    assert report.entries == (source, tree)
    assert report.orphan_temp_files_removed == ()
    assert source.read_bytes() == b"new source"
    assert tree.read_bytes() == b"new tree"
    assert not journal.exists()
    _assert_no_residue(source, tree)


def test_crash_before_journal_written_cleans_stray_temp(tmp_path: Path) -> None:
    """A crash before the journal itself is even written leaves only a
    stray ``.tmp`` sibling with no journal to describe a transaction.
    Recovery treats this as no transaction in flight and simply sweeps the
    orphan away, leaving the original target completely untouched."""

    source = tmp_path / "doc.src"
    source.write_bytes(b"old source")
    journal = tmp_path / "doc.journal"

    file_txn_module._stage_temp(file_txn_module._temp_path(source), b"new source")
    assert not journal.exists()

    report = recover([source], journal)

    assert report == RecoveryReport(
        action="none", journal_present=False, orphan_temp_files_removed=(file_txn_module._temp_path(source),)
    )
    assert source.read_bytes() == b"old source"
    assert not file_txn_module._temp_path(source).exists()


def test_recovery_idempotent(tmp_path: Path) -> None:
    """Running recovery a second time after a successful rollback or a
    successful roll-forward changes nothing: no journal remains after the
    first call, so the second is a true no-op on both branches."""

    # Rollback branch idempotency.
    source = tmp_path / "rb" / "doc.src"
    source.parent.mkdir()
    source.write_bytes(b"old")
    journal = tmp_path / "rb" / "doc.journal"
    _drive_partial_publish([FileWrite(source, b"new")], journal, renames_done=0)

    first = recover([source], journal)
    assert first.action == "rolled_back"
    before = source.read_bytes()
    second = recover([source], journal)
    assert second == RecoveryReport(action="none", journal_present=False)
    assert source.read_bytes() == before

    # Roll-forward branch idempotency.
    source2 = tmp_path / "fwd" / "doc.src"
    source2.parent.mkdir()
    source2.write_bytes(b"old")
    journal2 = tmp_path / "fwd" / "doc.journal"
    _drive_partial_publish([FileWrite(source2, b"new")], journal2, renames_done=1)

    first2 = recover([source2], journal2)
    assert first2.action == "rolled_forward"
    before2 = source2.read_bytes()
    second2 = recover([source2], journal2)
    assert second2 == RecoveryReport(action="none", journal_present=False)
    assert source2.read_bytes() == before2


def test_post_recovery_checksum_reverification(tmp_path: Path) -> None:
    """After recovery, rereading and rehashing every target from disk must
    match exactly what recovery claims to have restored -- rollback
    reproduces the old bytes' digest, roll-forward the new bytes' digest."""

    old_source, new_source = b"old source content", b"new source content"
    old_tree, new_tree = b"old tree content", b"new tree content"

    # Rollback case.
    source = tmp_path / "back" / "doc.src"
    tree = tmp_path / "back" / "doc.tree"
    source.parent.mkdir()
    source.write_bytes(old_source)
    tree.write_bytes(old_tree)
    journal = tmp_path / "back" / "doc.journal"
    _drive_partial_publish([FileWrite(source, new_source), FileWrite(tree, new_tree)], journal, renames_done=1)
    recover([source, tree], journal)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(old_source).hexdigest()
    assert hashlib.sha256(tree.read_bytes()).hexdigest() == hashlib.sha256(old_tree).hexdigest()

    # Roll-forward case.
    source2 = tmp_path / "fwd" / "doc.src"
    tree2 = tmp_path / "fwd" / "doc.tree"
    source2.parent.mkdir()
    source2.write_bytes(old_source)
    tree2.write_bytes(old_tree)
    journal2 = tmp_path / "fwd" / "doc.journal"
    _drive_partial_publish([FileWrite(source2, new_source), FileWrite(tree2, new_tree)], journal2, renames_done=2)
    recover([source2, tree2], journal2)
    assert hashlib.sha256(source2.read_bytes()).hexdigest() == hashlib.sha256(new_source).hexdigest()
    assert hashlib.sha256(tree2.read_bytes()).hexdigest() == hashlib.sha256(new_tree).hexdigest()


# ---- No torn reads, ever -----------------------------------------------------


def test_no_reader_observes_partial_write(tmp_path: Path) -> None:
    """A concurrent reader polling the target throughout a real ``publish``
    call must only ever observe the fully old bytes or the fully new bytes
    -- never a truncated or mixed read -- because the target is only ever
    touched by one atomic ``os.rename``, never written in place."""

    target = tmp_path / "big.src"
    journal = tmp_path / "doc.journal"
    old_content = b"O" * 2_000_000
    new_content = b"N" * 2_000_000
    target.write_bytes(old_content)

    observed: set = set()
    stop = threading.Event()

    def _reader() -> None:
        while not stop.is_set():
            try:
                observed.add(target.read_bytes())
            except FileNotFoundError:
                continue

    reader = threading.Thread(target=_reader)
    reader.start()
    try:
        publish([FileWrite(target, new_content)], journal)
    finally:
        stop.set()
        reader.join(timeout=5)

    assert observed <= {old_content, new_content}
    assert target.read_bytes() == new_content


# ---- Real filesystem failures -------------------------------------------------


def test_storage_io_error_with_path_and_phase(tmp_path: Path) -> None:
    """Real filesystem failures at different phases raise ``StorageIOError``
    carrying the ``STORAGE_IO_ERROR`` code plus the offending phase and
    path -- never a bare ``OSError`` escaping the module."""

    # (a) the target's own parent directory does not exist: fails staging
    # the target's temp file before the journal is ever touched.
    missing_target = tmp_path / "missing_dir" / "doc.src"
    journal_a = tmp_path / "a.journal"
    with pytest.raises(StorageIOError) as exc_a:
        publish([FileWrite(missing_target, b"data")], journal_a)
    assert exc_a.value.code == ErrorCode.STORAGE_IO_ERROR
    assert exc_a.value.phase == "stage_temp"
    assert exc_a.value.path == file_txn_module._temp_path(missing_target)
    assert not journal_a.exists()

    # (b) the journal's own parent directory does not exist: the entry's
    # own temp file stages fine (real residue, per the module's contract),
    # but the journal write fails at the same phase over its own temp path.
    source_b = tmp_path / "doc_b.src"
    source_b.write_bytes(b"original")
    bad_journal = tmp_path / "no_such_dir" / "b.journal"
    with pytest.raises(StorageIOError) as exc_b:
        publish([FileWrite(source_b, b"new")], bad_journal)
    assert exc_b.value.phase == "stage_temp"
    assert exc_b.value.path == file_txn_module._temp_path(bad_journal)
    assert file_txn_module._temp_path(source_b).exists()
    assert source_b.read_bytes() == b"original"
    # recover() is the documented way to clean up exactly this residue.
    report = recover([source_b], tmp_path / "cleanup.journal")
    assert report.orphan_temp_files_removed == (file_txn_module._temp_path(source_b),)

    # (c) the target is an existing directory: hard-linking a directory to
    # make its backup is never permitted by the OS, regardless of
    # permission bits, so this fails reliably at "backup_link".
    dir_target = tmp_path / "dir_target"
    dir_target.mkdir()
    journal_c = tmp_path / "c.journal"
    with pytest.raises(StorageIOError) as exc_c:
        publish([FileWrite(dir_target, b"new")], journal_c)
    assert exc_c.value.phase == "backup_link"
    assert exc_c.value.path == file_txn_module._backup_path(dir_target)
