"""The storage/mutable-tree join: persisted identity and the open decision.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.document_bridge`` as the facade actually drives it -- real temp
directories, real files copied verbatim out of ``src/tree_engine``, real plugins, real SHA-256
digests, real published tree files. Nothing is mocked and no toy document stands in for a real one:
the identity round trip runs over a shipped module of several hundred nodes, because a two-node
fixture cannot tell "identity was preserved" from "identity was reallocated in the same order".

Pinned hardest, each a permanent regression:

* **Identity survives a save and a reload.** Every node that outlives a mutation comes back with
  BOTH its ``node_id`` and its ``short_id``. Before this seam existed ``facade.load``/``save`` never
  reached the storage layer at all -- their own docstrings said so -- so a reload reparsed the
  source and ``reindex()`` minted a brand-new short_id map. Identity that is not persisted is not
  identity, and every address the editor hands out is a short_id.
* **The checksum decision, all four branches.** Matching, absent, and mismatched-with and
  mismatched-without a session holding the file: the last two are the owner's truth-priority rule
  and they must NOT collapse into one, because a mismatch means "reparse, the file won" before the
  file is open and "keep the tree, the file is stale" while it is.
* **An open never touches the source, and always brings the tree file up to date.** The source
  file's bytes AND its mtime survive every open unchanged -- it takes no part in the transaction --
  while the derived tree file is created when absent and refreshed when the source superseded it.
  That asymmetry is the invariant whose violation destroyed data on this project before, and it is
  what lets a read-only consumer keep identity and history without ever modifying what it reads.
  The byte-level open touches no filesystem at all, for a caller that cannot write even that.
* **A write reports every path it wrote, and leaves nothing else behind.** That set is what a
  caller owning atomicity elsewhere has to stage; a stray journal or backup would be a file it
  never learned about.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Tuple
from uuid import UUID

import pytest

import tree_engine.storage.lifecycle as lifecycle_module
from tree_engine import facade
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import TreeEngineException
from tree_engine.storage.document_bridge import OpenBranch, TreeWriteIntent
from tree_engine.storage.history import Checkpoint, CheckpointKind, HistoryPort

#: ``src/tree_engine`` itself; every source file under test is copied from here.
PACKAGE_ROOT = Path(lifecycle_module.__file__).resolve().parent.parent
REAL_MODULE = PACKAGE_ROOT / "core" / "short_id.py"
REAL_OTHER_MODULE = PACKAGE_ROOT / "core" / "identity.py"


def _copy_real(tmp_path: Path, real: Path, name: str = "") -> Path:
    """Copy a real ``src/tree_engine`` file into the temp directory verbatim."""
    target = tmp_path / (name or real.name)
    shutil.copyfile(real, target)
    return target


def _identity(document: facade.TreeDocument) -> Dict[UUID, int]:
    """Every node's ``node_id -> short_id`` pair, the whole of what must survive."""
    return {node_id: node.short_id for node_id, node in document.nodes_by_id.items()}


def _tree_file(source: Path) -> Path:
    return source.with_name(source.name + ".tree.json")


def _directory_state(root: Path) -> Dict[str, bytes]:
    """Every file under ``root``, by relative path, with its exact bytes."""
    return {str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.fixture
def python_source(tmp_path: Path) -> Path:
    """A real, several-hundred-node shipped module, copied byte for byte."""
    return _copy_real(tmp_path, REAL_MODULE)


def _mutated(document: facade.TreeDocument) -> None:
    """One real mutation: append a statement to the module body."""
    facade.insert(document, "TREE_ENGINE_MARKER = 1\n", position="last_child",
                  parent=document.root.short_id)


# -- 1. the identity round trip -------------------------------------------------


def test_identity_survives_mutate_save_reload_on_a_real_module(python_source: Path) -> None:
    """load -> mutate -> save -> reload: every surviving node keeps node_id AND short_id."""
    opened = facade.open_file(python_source)
    assert (opened.branch, opened.identity_preserved) == (OpenBranch.NO_SIDECAR, False)
    assert opened.tree_write_intent is TreeWriteIntent.CREATE
    document = opened.document
    before = _identity(document)
    assert len(before) > 200, f"the fixture must be a real module, got {len(before)} nodes"

    _mutated(document)
    after_edit = _identity(document)
    written = facade.write(document)
    assert written.written_paths == (python_source, _tree_file(python_source))

    reopened = facade.open_file(python_source)
    assert (reopened.branch, reopened.identity_preserved) == (OpenBranch.SHA_MATCH, True)
    assert reopened.tree_write_intent is TreeWriteIntent.NONE and reopened.refusal is None
    reloaded = _identity(reopened.document)

    assert reloaded == after_edit, "the reload must return the exact identity that was written"
    survivors = set(before) & set(reloaded)
    assert len(survivors) == len(before), "the mutation must not drop any pre-existing node_id"
    assert all(before[node_id] == reloaded[node_id] for node_id in survivors)
    assert facade.dumps(reopened.document) == python_source.read_bytes()
    assert reopened.document.document_id == document.document_id


def test_a_released_short_id_is_never_reissued_across_a_reload(python_source: Path) -> None:
    """{p097}: the monotonic counter is persisted, not just the issued values. Deriving the map
    from the tree's own nodes would recover every live short_id and reset the counter to just above
    the highest of them -- handing a value freed by a delete to the next inserted node."""
    document = facade.load(python_source)
    doomed = document.root.children[-1]
    freed = doomed.short_id
    facade.delete(document, doomed.short_id)
    facade.write(document)

    reloaded = facade.load(python_source)
    assert freed not in {node.short_id for node in reloaded.nodes_by_id.values()}
    _mutated(reloaded)
    issued = {node.short_id for node in reloaded.nodes_by_id.values()}
    assert freed not in issued, f"short_id {freed} was reissued after a delete and a reload"


# -- 2. the checksum decision, all four branches --------------------------------


def _stored_pair(python_source: Path) -> Tuple[bytes, bytes]:
    """Publish the pair once and hand back both files' bytes."""
    facade.write(facade.load(python_source))
    return python_source.read_bytes(), _tree_file(python_source).read_bytes()


def test_no_tree_file_rebuilds_from_source_with_fresh_identity(python_source: Path) -> None:
    """Branch 1 -- nothing stored, so the source is all there is."""
    outcome = facade.open_bytes(python_source.read_bytes(), file_path=str(python_source))
    assert outcome.branch is OpenBranch.NO_SIDECAR
    assert outcome.identity_preserved is False
    assert outcome.tree_write_intent is TreeWriteIntent.CREATE
    assert outcome.stored_source_sha256 is None and outcome.refusal is None


def test_matching_checksum_loads_the_stored_tree_with_identity_intact(
        python_source: Path) -> None:
    """Branch 2 -- the stored tree records these exact bytes, so it IS the document."""
    source_bytes, tree_bytes = _stored_pair(python_source)
    stored_identity = _identity(facade.load(python_source))

    outcome = facade.open_bytes(source_bytes, tree=tree_bytes, file_path=str(python_source))
    assert outcome.branch is OpenBranch.SHA_MATCH
    assert outcome.identity_preserved is True
    assert outcome.tree_write_intent is TreeWriteIntent.NONE
    assert outcome.stored_source_sha256 == outcome.source_sha256
    assert _identity(outcome.document) == stored_identity


def test_mismatch_without_a_session_rebuilds_because_the_file_is_the_truth(
        python_source: Path) -> None:
    """Branch 3 -- before a file is open the bytes on disk win, so identity is fresh."""
    _source_bytes, tree_bytes = _stored_pair(python_source)
    stored_identity = _identity(facade.load(python_source))
    changed = REAL_OTHER_MODULE.read_bytes()

    outcome = facade.open_bytes(changed, tree=tree_bytes, file_path=str(python_source),
                                active_session_holds_file=False)
    assert outcome.branch is OpenBranch.SHA_MISMATCH_NO_SESSION
    assert outcome.identity_preserved is False
    assert outcome.tree_write_intent is TreeWriteIntent.REPLACE
    assert outcome.stored_source_sha256 not in (None, outcome.source_sha256)
    assert "records source_sha256" in (outcome.refusal or "")
    assert set(_identity(outcome.document)) & set(stored_identity) == set()
    assert facade.dumps(outcome.document) == changed


def test_mismatch_with_an_active_session_keeps_the_stored_tree(python_source: Path) -> None:
    """Branch 4 -- while a session holds the file the TREE is the truth and the source on disk is
    the stale one, so the same mismatch must NOT reparse. Collapsing this into branch 3 would throw
    away the identity of every node in an open document the moment anything touched the file."""
    _source_bytes, tree_bytes = _stored_pair(python_source)
    stored_identity = _identity(facade.load(python_source))
    changed = REAL_OTHER_MODULE.read_bytes()

    outcome = facade.open_bytes(changed, tree=tree_bytes, file_path=str(python_source),
                                active_session_holds_file=True)
    assert outcome.branch is OpenBranch.SHA_MISMATCH_ACTIVE_SESSION
    assert outcome.identity_preserved is True
    assert outcome.tree_write_intent is TreeWriteIntent.NONE
    assert _identity(outcome.document) == stored_identity
    assert facade.dumps(outcome.document) == python_source.read_bytes() != changed


def test_an_unusable_tree_file_is_reported_as_none_with_the_gate_that_refused_it(
        python_source: Path) -> None:
    """A tree file that no gate would accept is not a stored tree at all, whatever a session
    thinks: there is nothing to keep, so both mismatch branches degrade to the rebuild -- and the
    refusal says which gate refused, so "rebuilt" is never reported without a reason."""
    source_bytes, _tree_bytes = _stored_pair(python_source)
    for damaged in (b"this is not a tree file at all", b"{}", b'{"envelope": {}}'):
        for holds in (False, True):
            outcome = facade.open_bytes(source_bytes, tree=damaged,
                                        file_path=str(python_source),
                                        active_session_holds_file=holds)
            assert outcome.branch is OpenBranch.NO_SIDECAR
            assert outcome.identity_preserved is False
            assert outcome.tree_write_intent is TreeWriteIntent.REPLACE
            assert outcome.refusal and "does not decode" in outcome.refusal


# -- 3. the source is immutable; the derived tree is persisted -------------------


def _source_facts(path: Path) -> Tuple[bytes, int]:
    """Everything about the source file an open must leave exactly as it found it."""
    return path.read_bytes(), path.stat().st_mtime_ns


def test_opening_a_file_with_no_tree_file_creates_it_and_never_touches_the_source(
        python_source: Path, tmp_path: Path) -> None:
    """The tree file is a derived artefact and IS persisted, because a consumer that reparses from
    scratch every time has no identity to hand out; the SOURCE is not the engine's to rewrite, so
    its bytes and its mtime are untouched. Both halves in one test, because it is the asymmetry
    between them that matters."""
    before = _source_facts(python_source)
    assert list(_directory_state(tmp_path)) == [python_source.name]

    outcome = facade.open_file(python_source)

    assert outcome.tree_write_intent is TreeWriteIntent.CREATE
    assert outcome.written_paths == (_tree_file(python_source),)
    assert _tree_file(python_source).exists()
    assert len(outcome.document.nodes_by_id) > 200
    assert facade.dumps(outcome.document) == python_source.read_bytes()
    assert _source_facts(python_source) == before
    assert set(_directory_state(tmp_path)) == {python_source.name, _tree_file(python_source).name}


def test_opening_over_a_stale_tree_file_refreshes_it_and_never_touches_the_source(
        python_source: Path) -> None:
    """A checksum mismatch with no session holding the file means the SOURCE won, so the tree file
    is rebuilt from it and rewritten -- and the source it was rebuilt from is still not written."""
    facade.write(facade.load(python_source))
    python_source.write_bytes(REAL_OTHER_MODULE.read_bytes())
    stale_tree = _tree_file(python_source).read_bytes()
    before = _source_facts(python_source)

    outcome = facade.open_file(python_source)

    assert outcome.branch is OpenBranch.SHA_MISMATCH_NO_SESSION
    assert outcome.tree_write_intent is TreeWriteIntent.REPLACE
    assert outcome.written_paths == (_tree_file(python_source),)
    assert _tree_file(python_source).read_bytes() != stale_tree
    assert facade.dumps(outcome.document) == python_source.read_bytes()
    assert _source_facts(python_source) == before
    assert facade.open_file(python_source).branch is OpenBranch.SHA_MATCH


def test_opening_an_up_to_date_pair_rewrites_nothing_at_all(python_source: Path,
                                                            tmp_path: Path) -> None:
    """The stored tree already IS the document, so there is no intent to act on and no file to
    touch: the whole directory, source and tree alike, comes through byte for byte."""
    facade.write(facade.load(python_source))
    before = _directory_state(tmp_path)
    source_before = _source_facts(python_source)

    outcome = facade.open_file(python_source)

    assert outcome.branch is OpenBranch.SHA_MATCH
    assert outcome.tree_write_intent is TreeWriteIntent.NONE
    assert outcome.written_paths == ()
    assert _directory_state(tmp_path) == before
    assert _source_facts(python_source) == source_before


def test_the_byte_level_open_touches_no_filesystem_at_all(tmp_path: Path) -> None:
    """``open_bytes`` is pure with respect to the filesystem even when it is given a path to name
    the format with: the caller holds the content, so nothing is read and nothing is written --
    and the tree file it would have created comes back as bytes for that caller to place."""
    empty = tmp_path / "workdir"
    empty.mkdir()
    named = empty / "short_id.py"

    outcome = facade.open_bytes(REAL_MODULE.read_bytes(), file_path=str(named))

    assert outcome.branch is OpenBranch.NO_SIDECAR
    assert outcome.tree_write_intent is TreeWriteIntent.CREATE
    assert outcome.tree_bytes is not None and outcome.written_paths == ()
    assert len(outcome.document.nodes_by_id) > 200
    assert _directory_state(empty) == {}


def test_the_tree_file_an_open_creates_is_the_one_the_next_open_accepts(
        python_source: Path) -> None:
    """The tree file an open persists must be accepted by the very next open -- otherwise every
    open would rewrite it and identity would never actually survive on the read-only path."""
    first = facade.open_file(python_source)
    second = facade.open_file(python_source)

    assert (first.branch, second.branch) == (OpenBranch.NO_SIDECAR, OpenBranch.SHA_MATCH)
    assert second.identity_preserved is True
    assert _identity(second.document) == _identity(first.document)


# -- 4. the write, and what it reports ------------------------------------------


def test_write_publishes_the_pair_and_reports_exactly_the_paths_it_wrote(
        python_source: Path, tmp_path: Path) -> None:
    """``written_paths`` is the whole of the change: the pair, and no journal, backup or temp file
    left behind for a caller to discover on its own when it stages the result."""
    document = facade.load(python_source)
    _mutated(document)

    written = facade.write(document)

    assert written.source_path == python_source
    assert written.tree_path == _tree_file(python_source)
    assert written.written_paths == (written.source_path, written.tree_path)
    assert set(_directory_state(tmp_path)) == {python_source.name, _tree_file(python_source).name}
    assert python_source.read_bytes() == written.source_bytes == facade.dumps(document)
    assert written.tree_payload_sha256 and len(written.tree_payload_sha256) == 64
    assert document.path == python_source and document.source_bytes == written.source_bytes


def test_write_to_a_new_path_publishes_a_pair_there_and_keeps_identity(
        python_source: Path, tmp_path: Path) -> None:
    """A save-as is still a paired write, so identity follows the document to its new home."""
    document = facade.load(python_source)
    identity = _identity(document)
    target = tmp_path / "renamed.py"

    written = facade.write(document, target)

    assert written.written_paths == (target, _tree_file(target))
    reopened = facade.open_file(target)
    assert reopened.branch is OpenBranch.SHA_MATCH
    assert _identity(reopened.document) == identity


def test_a_document_with_no_path_cannot_be_written(python_source: Path) -> None:
    """``loads`` produces a document that was never a file; writing it needs a path."""
    document = facade.loads(python_source.read_text(encoding="utf-8"), format_id="python")
    with pytest.raises(TreeEngineException) as failure:
        facade.write(document)
    assert failure.value.code is ErrorCode.STORAGE_IO_ERROR


# -- 5. the degraded representation round trip ----------------------------------


def test_a_fallback_document_keeps_its_diagnostic_across_a_write_and_reload(
        tmp_path: Path) -> None:
    """A document that degraded to plain text must still be able to say WHY after a reload. The
    diagnostic belongs to the representation, so it rides in the tree file's envelope metadata;
    without it a reopened fallback document silently looks like an ordinary plain-text one."""
    broken = tmp_path / "broken.py"
    broken.write_bytes(b"def broken(:\n    ???\n")
    opened = facade.open_file(broken)
    document = opened.document
    assert document.fallback_diagnostic is not None
    assert (document.source_format_id, document.format_id) == ("python", "plain_text")

    facade.write(document)
    reopened = facade.open_file(broken)

    assert reopened.branch is OpenBranch.SHA_MATCH and reopened.identity_preserved is True
    assert reopened.document.fallback_diagnostic == document.fallback_diagnostic
    assert (reopened.document.source_format_id, reopened.document.format_id) == (
        "python", "plain_text")
    assert facade.dumps(reopened.document) == b"def broken(:\n    ???\n"


def test_a_caller_that_declined_the_fallback_is_not_handed_one_out_of_storage(
        tmp_path: Path) -> None:
    """``allow_plain_text_fallback=False`` has to mean the same thing on both open branches. Once
    the degraded representation is persisted, accepting the stored tree would answer "no fallback"
    with a fallback -- the checksum matching says nothing about whether the caller wanted this
    representation. The stored tree is refused by name and the parse failure surfaces instead."""
    broken = tmp_path / "broken.py"
    broken.write_bytes(b"def broken(:\n    ???\n")
    assert facade.open_file(broken).written_paths == (_tree_file(broken),)

    assert facade.open_file(broken).branch is OpenBranch.SHA_MATCH
    with pytest.raises(TreeEngineException) as failure:
        facade.open_file(broken, allow_plain_text_fallback=False)
    assert failure.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert failure.value.plain_text_fallback_permitted is True


# -- 6. history: the engine records, the consumer stores ------------------------


class _RecordingHistory:
    """A real :class:`HistoryPort` implementation, not a mock: it keeps the checkpoints it is
    handed in a list, which is a history store as much as a repository is. What is under test is
    that the ENGINE calls the port at the two documented moments with the right artefacts, so the
    implementation only has to be honest, not elaborate."""

    def __init__(self) -> None:
        self.checkpoints: list = []

    def record_checkpoint(self, checkpoint: Checkpoint) -> str:
        self.checkpoints.append(checkpoint)
        return f"rev-{len(self.checkpoints)}"


def test_the_engine_records_a_checkpoint_at_open_and_after_every_write(
        python_source: Path) -> None:
    """History is the engine's own lifecycle, not something a consumer bolts on afterwards: a
    checkpoint at initialisation, so a rollback has a baseline, and one after each verified write."""
    history = _RecordingHistory()
    assert isinstance(history, HistoryPort), "the port is a real declared interface, not a shape"

    opened = facade.open_file(python_source, history=history)
    assert opened.checkpoint_id == "rev-1"
    assert [c.kind for c in history.checkpoints] == [CheckpointKind.OPEN]
    first = history.checkpoints[0]
    assert first.source_path == python_source
    assert first.source_bytes == python_source.read_bytes()
    assert first.source_sha256 == opened.source_sha256
    assert first.branch == OpenBranch.NO_SIDECAR.value
    assert first.written_paths == (_tree_file(python_source),)
    assert first.full is True and first.tree_bytes == _tree_file(python_source).read_bytes()

    _mutated(opened.document)
    written = facade.write(opened.document, history=history)

    assert written.checkpoint_id == "rev-2"
    assert [c.kind for c in history.checkpoints] == [CheckpointKind.OPEN, CheckpointKind.WRITE]
    second = history.checkpoints[1]
    assert second.written_paths == written.written_paths == (
        python_source, _tree_file(python_source))
    assert second.source_bytes == python_source.read_bytes() == facade.dumps(opened.document)
    assert second.tree_bytes == _tree_file(python_source).read_bytes()
    assert second.full is True
    assert second.document_id == first.document_id
    assert second.document_version > first.document_version


def test_with_no_history_port_nothing_is_recorded_and_nothing_else_changes(
        python_source: Path) -> None:
    """A consumer that keeps no history supplies no port; the engine then records nothing rather
    than quietly writing somewhere of its own choosing."""
    opened = facade.open_file(python_source)
    written = facade.write(opened.document)
    assert opened.checkpoint_id is None and written.checkpoint_id is None


def test_a_checkpoint_that_carries_no_tree_says_so_rather_than_looking_full(
        tmp_path: Path) -> None:
    """The two checkpoint shapes must stay distinguishable: an implementation routes a full one to
    a tree-and-source commit and a degraded one to a source-only commit, and recording a degraded
    checkpoint as full would silently claim identity is restorable from it when it is not."""
    history = _RecordingHistory()
    document = facade.loads("alpha\nbravo\n", format_id="plain_text")
    target = tmp_path / "notes.txt"

    written = facade.write(document, target, history=history)

    assert written.tree_path is not None and history.checkpoints[-1].full is True
    degraded = Checkpoint(kind=CheckpointKind.WRITE, document_id=document.document_id,
                          document_version=document.document_version, source_path=target,
                          source_bytes=b"alpha\n", source_sha256="0" * 64)
    assert degraded.full is False and degraded.written_paths == ()
