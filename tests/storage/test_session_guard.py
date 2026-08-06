"""Contract tests for the edit-session conflict guard (C-012, {p089}/{p094}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.session_guard`` end to end, against a real
temp directory, real files, and real SHA-256 digests -- no mock stands in
for :class:`EditSession` or the disk. The point pinned hardest: a verdict
is derived from content, never from size/mtime, so a same-size external
edit that restores the prior mtime is still caught, while content restored
byte-for-byte after an external round trip reads back as clean even though
its mtime necessarily moved.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (
    ChecksumMismatch,
    ConcurrentSourceModification,
    ConcurrentTreeModification,
    StorageIOError,
)
from tree_engine.storage.session_guard import (
    ConflictReport,
    ConflictResolutionPolicy,
    EditSession,
    FileEvidence,
    canonical_payload_bytes,
    source_sha256,
    tree_payload_sha256,
)

SOURCE_BYTES = b"def greet():\n    return 'hi'\n"
DOCUMENT: Dict[str, Any] = {"payload": {"a": 1, "nested": {"z": 9, "y": 8}}, "checksums": {"tree_payload_sha256": "0" * 64}}
DOCUMENT_V2: Dict[str, Any] = {"payload": {"a": 2, "nested": {"z": 9, "y": 8}}, "checksums": {"tree_payload_sha256": "1" * 64}}


def _tree_bytes(document: Dict[str, Any]) -> bytes:
    return json.dumps(document).encode("utf-8")


def _digest_pair(source: bytes, document: Dict[str, Any]) -> Tuple[str, str]:
    return source_sha256(source), tree_payload_sha256(canonical_payload_bytes(document))


def _make_pair(tmp_path: Path, source: bytes = SOURCE_BYTES, document: Dict[str, Any] = DOCUMENT) -> Tuple[Path, Path]:
    source_path = tmp_path / "doc.py"
    tree_path = tmp_path / "doc.tree.json"
    source_path.write_bytes(source)
    tree_path.write_bytes(_tree_bytes(document))
    return source_path, tree_path


def _flip_one_byte_same_size(path: Path) -> None:
    """Mutate one byte in place, preserving length, and restore mtime_ns exactly."""
    before = os.stat(path)
    data = bytearray(path.read_bytes())
    data[0] ^= 0xFF
    path.write_bytes(bytes(data))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


# ---- Dual-SHA verification ({p086}) ----------------------------------------

def test_dual_sha_verification(tmp_path: Path) -> None:
    """source_sha256 is byte-exact and changes on any content change;
    tree_payload_sha256 ignores the CHECKSUMS section and key order, so it
    stays stable across an unchanged canonical payload's re-serialization."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    assert session.base_source_sha256 == source_sha256(SOURCE_BYTES)
    assert session.base_tree_payload_sha256 == tree_payload_sha256(canonical_payload_bytes(DOCUMENT))

    # Same canonical payload, different CHECKSUMS content and JSON key order -> identical digest.
    reordered = {"checksums": {"tree_payload_sha256": "f" * 64}, "payload": {"a": 1, "nested": {"y": 8, "z": 9}}}
    assert tree_payload_sha256(canonical_payload_bytes(reordered)) == session.base_tree_payload_sha256

    # A one-byte source change moves source_sha256 even though size is unchanged.
    changed = bytearray(SOURCE_BYTES)
    changed[0] ^= 1
    assert source_sha256(bytes(changed)) != session.base_source_sha256
    assert len(changed) == len(SOURCE_BYTES)
    # Both helpers are pure: same bytes in, same digest out, every time.
    assert source_sha256(SOURCE_BYTES) == source_sha256(SOURCE_BYTES) == session.base_source_sha256


# ---- Session acceptance ({p089}) --------------------------------------------

def test_session_acceptance_matching_shas(tmp_path: Path) -> None:
    """A session opened with base SHAs matching the stored files allows a
    write: check_before_write returns cleanly and signals no conflict."""
    source_path, tree_path = _make_pair(tmp_path)
    base_source, base_tree = _digest_pair(SOURCE_BYTES, DOCUMENT)
    session = EditSession(source_path, tree_path, base_source_sha256=base_source, base_tree_payload_sha256=base_tree)
    report = session.check_before_write()
    assert isinstance(report, ConflictReport)
    assert not report.has_conflict
    assert report.error_code is None
    assert report.source_changed is False and report.tree_changed is False


# ---- Concurrent source modification ({p089}) --------------------------------

def test_concurrent_source_modification(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"# external edit\n")
    with pytest.raises(ConcurrentSourceModification) as excinfo:
        session.check_before_write()
    assert excinfo.value.code == ErrorCode.CONCURRENT_SOURCE_MODIFICATION
    # No write happened as a side effect of the failed check.
    assert tree_path.read_bytes() == _tree_bytes(DOCUMENT)


def test_source_byte_flip_same_size_same_mtime_still_refused(tmp_path: Path) -> None:
    """The hard case: same size, mtime restored exactly -- content, not metadata, must decide."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    before_stat = os.stat(source_path)
    _flip_one_byte_same_size(source_path)
    after_stat = os.stat(source_path)
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write()


def test_content_restored_after_external_round_trip_is_clean(tmp_path: Path) -> None:
    """Content is the truth: bytes overwritten then restored exactly reads back clean."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"# scratch\n")
    source_path.write_bytes(SOURCE_BYTES)  # external tool restores exact original bytes
    report = session.check_before_write()
    assert not report.has_conflict


def test_source_deleted_detected_with_correct_error(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.unlink()
    with pytest.raises(ConcurrentSourceModification) as excinfo:
        session.check_before_write()
    assert excinfo.value.details["exists"] is False
    assert excinfo.value.details["reason"] == "missing"


# ---- Concurrent tree modification ({p089}) -----------------------------------

def test_concurrent_tree_modification(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    with pytest.raises(ConcurrentTreeModification) as excinfo:
        session.check_before_write()
    assert excinfo.value.code == ErrorCode.CONCURRENT_TREE_MODIFICATION
    assert source_path.read_bytes() == SOURCE_BYTES


def test_tree_deleted_detected_with_correct_error(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    tree_path.unlink()
    with pytest.raises(ConcurrentTreeModification) as excinfo:
        session.check_before_write()
    assert excinfo.value.details["exists"] is False
    assert excinfo.value.details["reason"] == "missing"


@pytest.mark.parametrize("missing", ["source", "tree"])
def test_missing_file_at_open_raises_storage_io_error(tmp_path: Path, missing: str) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    (source_path if missing == "source" else tree_path).unlink()
    with pytest.raises(StorageIOError):
        EditSession(source_path, tree_path)


def test_externally_corrupted_tree_file_is_a_modification(tmp_path: Path) -> None:
    """Bytes that no longer canonicalize (not JSON/not a mapping) yield no
    digest, so the guard reports it as an external modification, not a
    crash and not a silent pass."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    tree_path.write_bytes(b"\xff\xfe not json at all")
    report = session.inspect()
    assert report.tree.exists is True
    assert report.tree.sha256 is None
    assert report.tree.unreadable_reason is not None
    assert report.tree_changed is True
    with pytest.raises(ConcurrentTreeModification) as excinfo:
        session.check_before_write()
    assert excinfo.value.details["current_tree_payload_sha256"] is None


# ---- Conflict resolution policy ({p089}) -------------------------------------

def test_conflict_policy_denied_by_default(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"x")
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write()  # policy defaults to REFUSE
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write(policy=ConflictResolutionPolicy.REFUSE)


@pytest.mark.parametrize("bogus_policy", [True, 1, "overwrite_both", None])
def test_bogus_policy_value_raises_type_error(tmp_path: Path, bogus_policy: Any) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    with pytest.raises(TypeError):
        session.check_before_write(policy=bogus_policy)


def test_policy_overwrite_source_covers_only_source(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"x")
    report = session.check_before_write(policy=ConflictResolutionPolicy.OVERWRITE_SOURCE)
    assert report.source_changed is True
    assert report.has_conflict is True  # has_conflict stays True; no exception was raised for it though
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    with pytest.raises(ConcurrentTreeModification):
        session.check_before_write(policy=ConflictResolutionPolicy.OVERWRITE_SOURCE)  # does not cover tree


def test_policy_overwrite_tree_covers_only_tree(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    report = session.check_before_write(policy=ConflictResolutionPolicy.OVERWRITE_TREE)
    assert report.tree_changed is True and report.has_conflict is True
    source_path.write_bytes(SOURCE_BYTES + b"x")
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write(policy=ConflictResolutionPolicy.OVERWRITE_TREE)  # does not cover source


def test_policy_overwrite_both_covers_both(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"x")
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    report = session.check_before_write(policy=ConflictResolutionPolicy.OVERWRITE_BOTH)
    assert report.source_changed and report.tree_changed and report.has_conflict


def test_source_checked_before_tree_when_both_changed(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    source_path.write_bytes(SOURCE_BYTES + b"x")
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write()


def test_conflict_resolution_policy_predicates() -> None:
    assert ConflictResolutionPolicy.REFUSE.allows_source_overwrite() is False
    assert ConflictResolutionPolicy.REFUSE.allows_tree_overwrite() is False
    assert ConflictResolutionPolicy.OVERWRITE_SOURCE.allows_source_overwrite() is True
    assert ConflictResolutionPolicy.OVERWRITE_SOURCE.allows_tree_overwrite() is False
    assert ConflictResolutionPolicy.OVERWRITE_TREE.allows_tree_overwrite() is True
    assert ConflictResolutionPolicy.OVERWRITE_TREE.allows_source_overwrite() is False
    assert ConflictResolutionPolicy.OVERWRITE_BOTH.allows_source_overwrite() is True
    assert ConflictResolutionPolicy.OVERWRITE_BOTH.allows_tree_overwrite() is True


# ---- accept_publication ({p091}) ---------------------------------------------

def test_accept_publication_advances_baseline_when_disk_matches(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    new_source = SOURCE_BYTES + b"# v2\n"
    source_path.write_bytes(new_source)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    expected_source, expected_tree = _digest_pair(new_source, DOCUMENT_V2)
    report = session.accept_publication(expected_source, expected_tree)
    assert not report.has_conflict
    assert session.base_source_sha256 == expected_source
    assert session.base_tree_payload_sha256 == expected_tree
    # The new baseline is what subsequent checks compare against.
    assert not session.check_before_write().has_conflict


def test_accept_publication_refuses_source_mismatch_and_keeps_baseline(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    old_base_source = session.base_source_sha256
    source_path.write_bytes(SOURCE_BYTES + b"# v2\n")  # actual disk content
    with pytest.raises(ChecksumMismatch):
        session.accept_publication("f" * 64, session.base_tree_payload_sha256)  # wrong claimed digest
    assert session.base_source_sha256 == old_base_source


def test_accept_publication_refuses_tree_mismatch_and_keeps_baseline(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    old_base_tree = session.base_tree_payload_sha256
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    with pytest.raises(ChecksumMismatch):
        session.accept_publication(session.base_source_sha256, "f" * 64)
    assert session.base_tree_payload_sha256 == old_base_tree


def test_base_value_update_after_accept(tmp_path: Path) -> None:
    """Subsequent checks compare against the NEW base values after accept,
    not the ones the session opened with."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    v2_source = SOURCE_BYTES + b"# v2\n"
    source_path.write_bytes(v2_source)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    expected_source, expected_tree = _digest_pair(v2_source, DOCUMENT_V2)
    session.accept_publication(expected_source, expected_tree)

    # Reverting to the ORIGINAL bytes now counts as a conflict, because the
    # baseline moved forward.
    source_path.write_bytes(SOURCE_BYTES)
    with pytest.raises(ConcurrentSourceModification):
        session.check_before_write()


# ---- Two concurrent sessions ({p089}, first publisher wins) -----------------

def test_two_concurrent_sessions_first_publisher_wins_second_refused(tmp_path: Path) -> None:
    source_path, tree_path = _make_pair(tmp_path)
    session_a = EditSession(source_path, tree_path)
    session_b = EditSession(source_path, tree_path)  # independent baseline, same pair

    # A publishes first.
    v2_source = SOURCE_BYTES + b"# from A\n"
    source_path.write_bytes(v2_source)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    expected_source, expected_tree = _digest_pair(v2_source, DOCUMENT_V2)
    session_a.accept_publication(expected_source, expected_tree)
    assert not session_a.check_before_write().has_conflict

    # B is still on the old baseline: refused, not silently merged.
    with pytest.raises(ConcurrentSourceModification):
        session_b.check_before_write()
    assert session_b.base_source_sha256 == source_sha256(SOURCE_BYTES)  # B's baseline never moved


# ---- Tree object / storage-layer boundary ({p025}) ---------------------------

def test_tree_object_carries_no_session_state(tmp_path: Path) -> None:
    """All base-digest and evidence state lives on the session, never on a
    tree object: the session's own attribute set never grows beyond its
    private fields, and the evidence dataclasses never carry a tree/node/
    document-shaped field."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    expected_keys = {
        "_source_path", "_tree_path", "_canonicalize", "_lock",
        "_base_source_sha256", "_base_tree_payload_sha256",
    }
    assert set(vars(session).keys()) == expected_keys

    session.inspect()
    session.check_before_write()
    new_source = SOURCE_BYTES + b"# v2\n"
    source_path.write_bytes(new_source)
    tree_path.write_bytes(_tree_bytes(DOCUMENT_V2))
    session.accept_publication(*_digest_pair(new_source, DOCUMENT_V2))

    assert set(vars(session).keys()) == expected_keys, "no tree/document state accrued on the session"
    forbidden_field_names = {"document", "node", "tree_object", "root"}
    for cls in (FileEvidence, ConflictReport):
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert not (field_names & forbidden_field_names), f"{cls.__name__} must not carry a tree object"


def test_session_base_digests_are_thread_safe_to_read_concurrently(tmp_path: Path) -> None:
    """Base-digest properties take the private lock: many threads reading
    them concurrently must never raise or observe a torn value."""
    source_path, tree_path = _make_pair(tmp_path)
    session = EditSession(source_path, tree_path)
    errors = []

    def _read_many() -> None:
        try:
            for _ in range(200):
                assert session.base_source_sha256 == source_sha256(SOURCE_BYTES)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_read_many) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
