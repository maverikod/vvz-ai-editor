"""Pipeline-level storage crash-recovery gate (C-012, {p094}, {p090}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: this check exercises the REAL recoverable-file-transaction protocol
in ``tree_engine.storage.file_txn`` (``publish``/``recover``/``FileWrite``,
per {p090}) and the REAL external-modification detector in
``tree_engine.storage.session_guard`` (per {p086}/{p089}/{p093}), against a
real temporary filesystem -- real files, real ``os.rename``/``os.link``
calls, never a mocked filesystem. It drives the storage API directly, the
same protocol steps the sibling pytest suites
(``tests/storage/test_file_txn.py``, ``tests/storage/test_session_guard.py``)
already cover in depth. Those pytest files remain the exhaustive contract
tests; this module is instead the pipeline-level acceptance gate: a
standalone subcommand runnable at any time against a working tree,
including from CI where pytest may not run, reporting a structured
per-case verdict rather than shelling out to pytest.

Every case below runs in its own fresh real temp directory (created with
``tempfile.mkdtemp`` and always removed in a ``finally``, even when the
case fails or raises) and reproduces a real crash by replaying
``file_txn``'s own private protocol steps only partway through and
stopping -- exactly the on-disk state a process crash at that point would
leave -- never by mocking any filesystem call.

Cases covered, each an independent named verdict:

* a clean multi-file publish leaving no journal/temp/backup residue;
* a crash before the journal is even written (stray ``.tmp`` only);
* a crash after the journal is written but before any publish rename
  (roll back to the untouched pre-transaction state);
* a crash between two entries' publish renames, which must never leave a
  mixed old+new pair (roll back both, never a torn result);
* a crash after every publish rename but before finalize (roll forward,
  keeping the new bytes);
* recovery being idempotent: a second ``recover()`` call after either a
  rollback or a roll-forward is a true no-op;
* an external source modification being refused by ``EditSession``;
* the hard case: a same-size, same-mtime one-byte external change is still
  refused, because the verdict is derived from content, never metadata
  ({p093}).

The check registers itself on the shared pipeline registry (see
``pipeline/registry.py``) and reports through ``CheckResult``/
``CheckStatus`` only -- it never prints or calls ``sys.exit`` itself; the
pipeline CLI owns all console output and process exit codes.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Callable, List, Sequence

from pipeline import registry
from pipeline.registry import CheckResult
from tree_engine.exceptions import ConcurrentSourceModification
from tree_engine.storage import file_txn as file_txn_module
from tree_engine.storage.file_txn import FileWrite, RecoveryReport, publish, recover
from tree_engine.storage.session_guard import EditSession

CHECK_NAME = "check-recovery"
CHECK_DESCRIPTION = (
    "Exercise the real storage recovery matrix ({p094}, {p090}) against a "
    "real temporary filesystem: file_txn publish/crash/recover paths and "
    "the session_guard external-modification detector, including the "
    "same-size same-mtime hard case."
)


@dataclasses.dataclass(frozen=True)
class CaseResult:
    """One named case's verdict: pass/fail plus a short human detail."""

    name: str
    passed: bool
    detail: str = ""

    def format(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        head = f"[{status}] {self.name}"
        return f"{head} - {self.detail}" if self.detail else head


def _run_case(name: str, func: Callable[[Path], None]) -> CaseResult:
    """Run one case in its own fresh real temp directory; always clean up,
    even when the case fails or raises, so the check leaves zero residue."""

    tmp_dir = Path(tempfile.mkdtemp(prefix="check-recovery-"))
    try:
        func(tmp_dir)
        return CaseResult(name, True, "ok")
    except AssertionError as exc:
        return CaseResult(name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is a case failure
        return CaseResult(name, False, f"unexpected exception:\n{traceback.format_exc()}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _drive_partial_publish(
    files: Sequence[FileWrite], journal: Path, *, renames_done: int
) -> List["file_txn_module._PlanEntry"]:
    """Replay ``publish()``'s own real protocol -- stage, journal, backup,
    then only the first ``renames_done`` publish-renames -- and stop. This
    is the exact on-disk state a process crash at that point would leave,
    produced with the module's own real steps against the real filesystem."""

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


def _flip_one_byte_same_size(path: Path) -> None:
    """Mutate one byte in place, preserving length, and restore mtime_ns
    exactly -- the hard case a content-only verdict must still catch."""

    before = os.stat(path)
    data = bytearray(path.read_bytes())
    data[0] ^= 0xFF
    path.write_bytes(bytes(data))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


# ---- file_txn cases ---------------------------------------------------------


def _case_clean_multi_file_publish(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    journal = tmp_dir / "doc.journal"
    source.write_bytes(b"old source bytes")
    tree.write_bytes(b"old tree bytes")

    publish([FileWrite(source, b"new source bytes"), FileWrite(tree, b"new tree bytes")], journal)

    assert source.read_bytes() == b"new source bytes"
    assert tree.read_bytes() == b"new tree bytes"
    assert not journal.exists()
    for target in (source, tree):
        assert not file_txn_module._temp_path(target).exists()
        assert not file_txn_module._backup_path(target).exists()

    report = recover([source, tree], journal)
    assert report == RecoveryReport(action="none", journal_present=False)


def _case_crash_before_journal_written(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    journal = tmp_dir / "doc.journal"
    source.write_bytes(b"old source")

    file_txn_module._stage_temp(file_txn_module._temp_path(source), b"new source")
    assert not journal.exists()

    report = recover([source], journal)

    assert report.action == "none"
    assert report.journal_present is False
    assert report.orphan_temp_files_removed == (file_txn_module._temp_path(source),)
    assert source.read_bytes() == b"old source"
    assert not file_txn_module._temp_path(source).exists()


def _case_crash_before_first_rename(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    journal = tmp_dir / "doc.journal"
    source.write_bytes(b"old source")
    tree.write_bytes(b"old tree")
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    _drive_partial_publish(files, journal, renames_done=0)

    report = recover([source, tree], journal)

    assert report.action == "rolled_back"
    assert report.entries == (source, tree)
    assert source.read_bytes() == b"old source"
    assert tree.read_bytes() == b"old tree"
    assert not journal.exists()


def _case_crash_between_renames(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    journal = tmp_dir / "doc.journal"
    source.write_bytes(b"old source")
    tree.write_bytes(b"old tree")
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    _drive_partial_publish(files, journal, renames_done=1)
    # Mid-crash sanity: exactly the torn state a real crash leaves.
    assert source.read_bytes() == b"new source"
    assert tree.read_bytes() == b"old tree"

    report = recover([source, tree], journal)

    assert report.action == "rolled_back"
    assert report.entries == (source, tree)
    assert source.read_bytes() == b"old source"
    assert tree.read_bytes() == b"old tree"
    assert not journal.exists()


def _case_crash_after_all_renames(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    journal = tmp_dir / "doc.journal"
    source.write_bytes(b"old source")
    tree.write_bytes(b"old tree")
    files = [FileWrite(source, b"new source"), FileWrite(tree, b"new tree")]

    _drive_partial_publish(files, journal, renames_done=2)

    report = recover([source, tree], journal)

    assert report.action == "rolled_forward"
    assert report.entries == (source, tree)
    assert report.orphan_temp_files_removed == ()
    assert source.read_bytes() == b"new source"
    assert tree.read_bytes() == b"new tree"
    assert not journal.exists()


def _case_recovery_is_idempotent(tmp_dir: Path) -> None:
    # Rollback branch idempotency.
    source = tmp_dir / "rb" / "doc.src"
    source.parent.mkdir()
    source.write_bytes(b"old")
    journal = tmp_dir / "rb" / "doc.journal"
    _drive_partial_publish([FileWrite(source, b"new")], journal, renames_done=0)

    first = recover([source], journal)
    assert first.action == "rolled_back"
    before = source.read_bytes()
    second = recover([source], journal)
    assert second == RecoveryReport(action="none", journal_present=False)
    assert source.read_bytes() == before

    # Roll-forward branch idempotency.
    source2 = tmp_dir / "fwd" / "doc.src"
    source2.parent.mkdir()
    source2.write_bytes(b"old")
    journal2 = tmp_dir / "fwd" / "doc.journal"
    _drive_partial_publish([FileWrite(source2, b"new")], journal2, renames_done=1)

    first2 = recover([source2], journal2)
    assert first2.action == "rolled_forward"
    before2 = source2.read_bytes()
    second2 = recover([source2], journal2)
    assert second2 == RecoveryReport(action="none", journal_present=False)
    assert source2.read_bytes() == before2


# ---- session_guard cases -----------------------------------------------------


def _case_external_source_modification_refused(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    source.write_bytes(b"def greet():\n    return 'hi'\n")
    tree.write_bytes(b'{"a": 1}')

    session = EditSession(source, tree)
    source.write_bytes(source.read_bytes() + b"# external edit\n")

    try:
        session.check_before_write()
    except ConcurrentSourceModification:
        pass
    else:
        raise AssertionError("expected ConcurrentSourceModification for an external edit")


def _case_external_modification_same_size_same_mtime(tmp_dir: Path) -> None:
    source = tmp_dir / "doc.src"
    tree = tmp_dir / "doc.tree"
    source.write_bytes(b"def greet():\n    return 'hi'\n")
    tree.write_bytes(b'{"a": 1}')

    session = EditSession(source, tree)
    before_stat = os.stat(source)
    _flip_one_byte_same_size(source)
    after_stat = os.stat(source)
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns

    try:
        session.check_before_write()
    except ConcurrentSourceModification:
        pass
    else:
        raise AssertionError(
            "expected ConcurrentSourceModification for a same-size, same-mtime byte flip"
        )


# ---- check entry point -------------------------------------------------------

_CASES = (
    ("clean_multi_file_publish_no_residue", _case_clean_multi_file_publish),
    ("crash_before_journal_written", _case_crash_before_journal_written),
    ("crash_before_first_rename_rolls_back", _case_crash_before_first_rename),
    ("crash_between_renames_rolls_back", _case_crash_between_renames),
    ("crash_after_all_renames_rolls_forward", _case_crash_after_all_renames),
    ("recovery_is_idempotent", _case_recovery_is_idempotent),
    ("external_source_modification_refused", _case_external_source_modification_refused),
    (
        "external_modification_same_size_same_mtime_refused",
        _case_external_modification_same_size_same_mtime,
    ),
)


def check_recovery() -> CheckResult:
    """Run the full storage recovery case matrix and report one verdict.

    Every case runs independently (a failing case never aborts the rest)
    against its own real temporary directory, which is always removed
    afterward regardless of outcome.
    """

    results = [_run_case(name, func) for name, func in _CASES]
    output = "\n".join(result.format() for result in results)
    failed = [result for result in results if not result.passed]
    passed_count = len(results) - len(failed)

    if not failed:
        return CheckResult.ok(
            message=f"{passed_count}/{len(results)} storage recovery case(s) passed",
            output=output,
        )
    return CheckResult.fail(
        message=(
            f"{len(failed)}/{len(results)} storage recovery case(s) failed: "
            f"{', '.join(result.name for result in failed)}"
        ),
        output=output,
    )


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_recovery)
