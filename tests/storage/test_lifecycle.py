"""Contract tests for the storage lifecycle of the source/tree pair (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.storage.lifecycle`` end to end -- real temp directories,
real files copied verbatim out of ``src/tree_engine``, real plugins, real
SHA-256 digests. Three formats run over real bytes: ``python`` over a shipped
module, ``plain_text`` over that same module under a ``.txt`` name (the package
ships no non-``.py`` file of its own), and ``json`` over a document built from
the package's own module inventory. Nothing is mocked except the one thing that
cannot be produced otherwise -- a process crash *between* the pair's two publish
renames, made by failing the ``os.rename`` ``file_txn`` calls on the second
published target. Plugins are never stubbed: ``_CountingPlugin`` is a delegating
spy counting ``parse_document`` calls, so "the fast path did not reparse" is an
observed fact and not an inference.

Pinned hardest, each a permanent regression: open -> save -> reload preserves
every ``node_id``/``short_id`` and the reloaded tree renders back to the bytes
on disk; a crash between the two publish renames leaves a torn pair the next
open rolls back with no residue, after which saving still works; an outside
writer is refused even when its edit keeps size and mtime; a fallback document
saves BYTE-EXACT with full identity, which was a real data-loss hazard; and
``file_txn``'s own module-local ``StorageIOError`` is translated into the typed
hierarchy.

Source-of-truth labels honored here: {p085}-{p094}, {p100}.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
from pathlib import Path
from typing import Any, List, Set, Tuple

import pytest

import tree_engine.storage.file_txn as file_txn_module
import tree_engine.storage.session_guard as session_guard_module
from tree_engine.core.nodes import Document, walk
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (
    ConcurrentSourceModification, ConcurrentTreeModification, FormatPluginContractError,
    FormatPluginNotFound, StorageIOError, TreeEngineException, TreeSchemaUnsupported)
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.storage.codec import decode
from tree_engine.storage.lifecycle import (
    DEFAULT_JOURNAL_SUFFIX, DEFAULT_TREE_SUFFIX, OpenedDocument, StorageLifecycle,
    canonical_tree_payload, validate_structure)
from tree_engine.storage.session_guard import (
    ConflictResolutionPolicy, source_sha256, tree_payload_sha256)

#: ``src/tree_engine`` itself; every source file under test is copied from here.
PACKAGE_ROOT = Path(session_guard_module.__file__).resolve().parent.parent
REAL_MODULE = PACKAGE_ROOT / "storage" / "session_guard.py"
REAL_OTHER_MODULE = PACKAGE_ROOT / "plugins" / "fallback.py"
UNPARSABLE = REAL_MODULE.read_bytes()[:2000] + b"\ndef broken(:\n    ???\n"
EDITED_SOURCE = b"EDITED = True\n\n\ndef added() -> int:\n    return 7\n"
ALL_PLUGINS = (PYTHON_FORMAT_PLUGIN, PLAIN_TEXT_FORMAT_PLUGIN, JSON_FORMAT_PLUGIN)
RENDERERS = {"plain_text": PLAIN_TEXT_FORMAT_PLUGIN, "json": JSON_FORMAT_PLUGIN}

class _CountingPlugin:
    """The real plugin, wrapped so a test can observe whether it parsed. A spy,
    not a mock: every call reaches the wrapped plugin and nothing is replaced.
    Only ``parse_document`` is counted -- what {p087}'s fast path must not reach."""
    def __init__(self, inner: Any) -> None:
        self._inner, self.parse_calls = inner, 0

    @property
    def metadata(self) -> Any:
        return self._inner.metadata

    def parse_document(self, *args: Any, **kwargs: Any) -> Any:
        self.parse_calls += 1
        return self._inner.parse_document(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

def _lifecycle(*plugins: Any) -> StorageLifecycle:
    """A lifecycle over a real registry; no plugins given means all three."""
    registry = FormatPluginRegistry()
    for plugin in plugins or ALL_PLUGINS:
        registry.register_format_plugin(plugin)
    return StorageLifecycle(registry)

@pytest.fixture
def lifecycle() -> StorageLifecycle:
    return _lifecycle()

def _copy_real(tmp_path: Path, real: Path, name: str = "") -> Path:
    """Copy a real ``src/tree_engine`` file into the temp directory verbatim."""
    target = tmp_path / (name or real.name)
    shutil.copyfile(real, target)
    return target

@pytest.fixture
def python_source(tmp_path: Path) -> Path:
    return _copy_real(tmp_path, REAL_MODULE)

@pytest.fixture
def unparsable_source(tmp_path: Path) -> Path:
    """Real Python bytes damaged into something the python plugin cannot parse."""
    target = tmp_path / "damaged.py"
    target.write_bytes(UNPARSABLE)
    return target

def _json_inventory(tmp_path: Path) -> Path:
    """A real JSON document: the package's own module inventory."""
    modules = sorted(p.relative_to(PACKAGE_ROOT).as_posix() for p in PACKAGE_ROOT.rglob("*.py"))
    text = json.dumps({"package": "tree_engine", "modules": modules}, indent=2)
    (target := tmp_path / "inventory.json").write_bytes(text.encode("utf-8") + b"\n")
    return target

def _identity(document: Document) -> List[Tuple[Any, Any]]:
    """Every node's ``(node_id, short_id)`` in walk order ({p092}, {p097})."""
    return [(node.node_id, node.short_id) for node in walk(document.root)]

def _fully_identified(document: Document) -> bool:
    return bool(_identity(document)) and all(a and b for a, b in _identity(document))

def _patch_tree(path: Path, section: str, key: str, value: Any) -> None:
    """Rewrite one field of a tree file on disk, exactly as an outside writer would."""
    data = json.loads(path.read_bytes().decode("utf-8"))
    target = data["envelope"] if section == "envelope" else data["payload"]["tree"]["root"]
    target[key] = value
    path.write_bytes(json.dumps(data).encode("utf-8"))

def _assert_no_residue(opened: OpenedDocument) -> None:
    """The pair and nothing else: no journal, no ``.tmp``, no ``.bak``."""
    assert not opened.journal_path.exists()
    assert (sorted(p.name for p in opened.source_path.parent.iterdir())
            == sorted([opened.source_path.name, opened.tree_path.name]))

def _crash_between_publish_renames(monkeypatch: pytest.MonkeyPatch, targets: Set[Path]) -> None:
    """Make the pair's SECOND publish rename fail: a crash after the source file
    was swapped but before the tree file was ({p090}). The only patched call in
    this file; the journal rename and the backup links stay entirely real."""
    real_rename = os.rename
    published = {"count": 0}

    def rename(src: Any, dst: Any) -> None:
        if Path(dst) in targets:
            published["count"] += 1
            if published["count"] == 2:
                raise OSError(errno.EIO, "simulated crash between the two publish renames")
        real_rename(src, dst)

    monkeypatch.setattr(file_txn_module.os, "rename", rename)

def test_fast_path_skips_the_parser_while_explicit_reparse_forces_it(tmp_path: Path) -> None:
    """{p087}: a stored, valid tree file is accepted without ``parse_document``;
    {p037}: ``reparse``/``explicit_reparse`` force the rebuild branch anyway."""
    spy = _CountingPlugin(PYTHON_FORMAT_PLUGIN)
    lifecycle = _lifecycle(spy, PLAIN_TEXT_FORMAT_PLUGIN)
    source = _copy_real(tmp_path, REAL_MODULE)
    first = lifecycle.open(source)
    assert first.rebuilt is True and spy.parse_calls == 1
    assert first.tree_path == Path(str(source) + DEFAULT_TREE_SUFFIX)
    assert first.journal_path == Path(str(source) + DEFAULT_JOURNAL_SUFFIX)
    second = lifecycle.open(source)
    assert second.rebuilt is False and spy.parse_calls == 1
    assert _identity(second.document) == _identity(first.document)
    _assert_no_residue(second)
    assert lifecycle.reparse(source).rebuilt is True and spy.parse_calls == 2
    assert StorageLifecycle.explicit_reparse is StorageLifecycle.reparse
    assert lifecycle.open(source).rebuilt is False and spy.parse_calls == 2

def test_full_cycle_preserves_identity_and_renders_back_to_the_saved_bytes(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """Open, save, reload a real module: every node_id/short_id survives and the
    reloaded tree renders back to exactly the bytes on disk ({p091}, {p092})."""
    original = REAL_MODULE.read_bytes()
    opened = lifecycle.open(python_source)
    before = _identity(opened.document)
    saved = lifecycle.save(opened)
    assert python_source.read_bytes() == original
    assert saved.envelope.document_version == opened.envelope.document_version + 1
    assert saved.envelope.document_id == opened.envelope.document_id
    reloaded = lifecycle.open(python_source)
    assert reloaded.rebuilt is False
    assert _identity(reloaded.document) == before and _fully_identified(reloaded.document)
    assert PYTHON_FORMAT_PLUGIN.render_document(reloaded.document) == python_source.read_bytes()
    assert reloaded.source_sha256 == source_sha256(python_source.read_bytes())
    _assert_no_residue(reloaded)

@pytest.mark.parametrize("format_id", ["plain_text", "json"])
def test_second_format_round_trips_byte_exactly(
        lifecycle: StorageLifecycle, tmp_path: Path, format_id: str) -> None:
    """Further formats over real bytes: that module read as ``plain_text``, and
    the package's own inventory read as ``json``."""
    source = (_copy_real(tmp_path, REAL_MODULE, name="session_guard.txt")
              if format_id == "plain_text" else _json_inventory(tmp_path))
    original = source.read_bytes()
    opened = lifecycle.open(source)
    assert opened.format_id == format_id and opened.fallback is False
    lifecycle.save(opened)
    assert source.read_bytes() == original
    reloaded = lifecycle.open(source)
    assert reloaded.rebuilt is False
    assert _identity(reloaded.document) == _identity(opened.document)
    assert RENDERERS[format_id].render_document(reloaded.document) == original

def test_returned_tree_is_the_revalidated_one_and_carries_no_file_state(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """{p088}/{p094}: what a rebuild returns is what it published and reread; and
    {p025}/{p093}: paths, digests and session state live on the storage object."""
    opened = lifecycle.open(python_source)
    tree_bytes = opened.tree_path.read_bytes()
    published = decode(tree_bytes)
    assert opened.rebuilt is True
    assert _identity(published.document) == _identity(opened.document)
    assert published.checksums.source_sha256 == opened.source_sha256
    assert opened.tree_payload_sha256 == tree_payload_sha256(canonical_tree_payload(tree_bytes))
    validate_structure(opened.document)
    assert opened.source_path == python_source and opened.session.source_path == python_source
    assert opened.session.base_source_sha256 == opened.source_sha256
    assert sorted(vars(opened.document)) == [
        "document_id", "representation_format_id", "root", "source_format_id"]
    assert not any(hasattr(opened.document, leaked) for leaked in
                   ("source_path", "tree_path", "sha256", "session", "mtime"))

@pytest.mark.parametrize("damage", ["missing", "corrupt_payload", "truncated", "garbage",
                                   "stale_source_sha256", "old_plugin_version"])
def test_absent_stale_or_damaged_tree_file_is_rebuilt_not_returned_broken(
        lifecycle: StorageLifecycle, python_source: Path, damage: str) -> None:
    """{p087}/{p088}: a missing, corrupt, truncated, unparsable, source-stale or
    version-stale tree file is rebuilt and republished; nothing broken is returned."""
    opened = lifecycle.open(python_source)
    tree_path, raw = opened.tree_path, opened.tree_path.read_bytes()
    if damage == "missing":
        tree_path.unlink()
    elif damage == "corrupt_payload":
        _patch_tree(tree_path, "payload", "children", "not a list")
    elif damage == "truncated":
        tree_path.write_bytes(raw[: len(raw) // 2])
    elif damage == "garbage":
        tree_path.write_bytes(b"this is not a tree file at all")
    elif damage == "stale_source_sha256":
        python_source.write_bytes(REAL_OTHER_MODULE.read_bytes())
    else:
        _patch_tree(tree_path, "envelope", "plugin_version", "0.0.1-ancient")
    rebuilt = lifecycle.open(python_source)
    assert rebuilt.rebuilt is True and _fully_identified(rebuilt.document)
    assert PYTHON_FORMAT_PLUGIN.render_document(rebuilt.document) == python_source.read_bytes()
    assert rebuilt.source_sha256 == source_sha256(python_source.read_bytes())
    assert decode(tree_path.read_bytes()).checksums.source_sha256 == rebuilt.source_sha256
    assert rebuilt.envelope.plugin_version == PYTHON_FORMAT_PLUGIN.metadata.plugin_version
    assert lifecycle.open(python_source).rebuilt is False
    _assert_no_residue(rebuilt)

@pytest.mark.parametrize("key, value, error, code", [
    ("schema_version", "99.0", TreeSchemaUnsupported, ErrorCode.TREE_SCHEMA_UNSUPPORTED),
    ("plugin_contract_version", "9.0.0", FormatPluginContractError,
     ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR)])
def test_a_tree_file_this_build_must_not_reinterpret_is_raised_not_rebuilt(
        lifecycle: StorageLifecycle, python_source: Path,
        key: str, value: str, error: type, code: ErrorCode) -> None:
    """{p087}/{p100}: an unknown major schema and an incompatible plugin contract
    major each raise their own typed error instead of being rebuilt away."""
    opened = lifecycle.open(python_source)
    _patch_tree(opened.tree_path, "envelope", key, value)
    with pytest.raises(error) as info:
        lifecycle.open(python_source)
    assert info.value.code is code

def test_compatible_minor_schema_keeps_the_fast_path(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """{p100}: a minor bump inside the supported major is still accepted."""
    opened = lifecycle.open(python_source)
    _patch_tree(opened.tree_path, "envelope", "schema_version", "1.7")
    reopened = lifecycle.open(python_source)
    assert reopened.rebuilt is False and reopened.envelope.schema_version == "1.7"

def test_absent_representation_plugin_is_refused_without_fallback(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """{p087}: a missing backend plugin is FORMAT_PLUGIN_NOT_FOUND -- never a
    plain-text fallback and never a rebuild."""
    lifecycle.open(python_source)
    without_python = _lifecycle(JSON_FORMAT_PLUGIN, PLAIN_TEXT_FORMAT_PLUGIN)
    with pytest.raises(FormatPluginNotFound) as info:
        without_python.open(python_source, format_id="json")
    assert info.value.code is ErrorCode.FORMAT_PLUGIN_NOT_FOUND

def test_missing_source_file_is_a_typed_storage_io_error(
        lifecycle: StorageLifecycle, tmp_path: Path) -> None:
    """An absent source is reported with its own typed error and a real code."""
    with pytest.raises(StorageIOError) as info:
        lifecycle.open(tmp_path / "not-there.py")
    assert info.value.code is ErrorCode.STORAGE_IO_ERROR
    assert info.value.details["phase"] == "read"

def test_fallback_keeps_identity_saves_byte_exact_and_reloads_without_the_parser(
        unparsable_source: Path) -> None:
    """{p088}/{p060}/{p094}: FORMAT_CONTENT_PARSE_FAILED degrades to plain_text,
    keeps the source format and gives every node a node_id AND a short_id; the
    fallback representation is resolved through the registry, so a registry
    holding only the source plugin refuses instead of degrading; saving such a
    document is BYTE-EXACT -- it was a real data-loss hazard -- and reopening it
    takes the fast path without ever reaching the original parser again."""
    with pytest.raises(FormatPluginNotFound) as info:
        _lifecycle(PYTHON_FORMAT_PLUGIN).open(unparsable_source)
    assert info.value.code is ErrorCode.FORMAT_PLUGIN_NOT_FOUND
    spy = _CountingPlugin(PYTHON_FORMAT_PLUGIN)
    lifecycle = _lifecycle(spy, PLAIN_TEXT_FORMAT_PLUGIN)
    assert not lifecycle.tree_path_for(unparsable_source).exists()
    opened = lifecycle.open(unparsable_source)
    assert opened.fallback is True and opened.rebuilt is True and spy.parse_calls == 1
    assert opened.format_id == "python" and opened.document.source_format_id == "python"
    assert opened.document.representation_format_id == "plain_text"
    assert opened.envelope.plugin_id == "plain_text" and _fully_identified(opened.document)
    assert lifecycle.save(opened).fallback is True
    assert unparsable_source.read_bytes() == UNPARSABLE
    reopened = lifecycle.open(unparsable_source)
    assert reopened.rebuilt is False and reopened.fallback is True and spy.parse_calls == 1
    assert _identity(reopened.document) == _identity(opened.document)
    assert unparsable_source.read_bytes() == UNPARSABLE

def test_outside_writer_is_refused_even_at_the_same_size_and_mtime(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """{p089}/{p093}: the verdict comes from content, never from metadata."""
    opened = lifecycle.open(python_source)
    before = os.stat(python_source)
    data = bytearray(python_source.read_bytes())
    data[0] ^= 0x20
    python_source.write_bytes(bytes(data))
    os.utime(python_source, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(python_source)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    with pytest.raises(ConcurrentSourceModification) as info:
        lifecycle.save(opened)
    assert info.value.code is ErrorCode.CONCURRENT_SOURCE_MODIFICATION
    assert python_source.read_bytes() == bytes(data), "a refused save must not write"

def test_external_tree_edit_refuses_save_until_a_policy_names_the_overwrite(
        lifecycle: StorageLifecycle, python_source: Path) -> None:
    """{p089}: CONCURRENT_TREE_MODIFICATION, overridable only by naming a policy."""
    opened = lifecycle.open(python_source)
    _patch_tree(opened.tree_path, "payload", "extended_type", "externally-touched")
    with pytest.raises(ConcurrentTreeModification) as info:
        lifecycle.save(opened)
    assert info.value.code is ErrorCode.CONCURRENT_TREE_MODIFICATION
    saved = lifecycle.save(opened, policy=ConflictResolutionPolicy.OVERWRITE_TREE)
    assert saved.envelope.document_version == opened.envelope.document_version + 1
    assert lifecycle.open(python_source).rebuilt is False

def test_crash_between_the_publish_renames_is_rolled_back_on_the_next_open(
        lifecycle: StorageLifecycle, python_source: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """{p090}: a torn pair is detected and undone at the next open, leaves no
    residue behind, and the pair is fully usable afterwards."""
    opened = lifecycle.open(python_source)
    source_before, tree_before = python_source.read_bytes(), opened.tree_path.read_bytes()
    edited = PYTHON_FORMAT_PLUGIN.parse_document(EDITED_SOURCE, source_format_id="python")
    _crash_between_publish_renames(monkeypatch, {python_source, opened.tree_path})
    with pytest.raises(StorageIOError) as info:
        lifecycle.save(opened, edited)
    monkeypatch.undo()
    assert info.value.details["phase"] == "publish_rename"
    assert python_source.read_bytes() != source_before, "the pair really is torn"
    assert opened.tree_path.read_bytes() == tree_before and opened.journal_path.exists()
    recovered = lifecycle.open(python_source)
    assert recovered.recovery.action == "rolled_back" and recovered.recovery.journal_present
    assert set(recovered.recovery.entries) == {python_source, opened.tree_path}
    assert python_source.read_bytes() == source_before
    assert opened.tree_path.read_bytes() == tree_before and recovered.rebuilt is False
    _assert_no_residue(recovered)
    saved = lifecycle.save(recovered, edited)
    assert python_source.read_bytes() == EDITED_SOURCE
    assert lifecycle.open(python_source).rebuilt is False
    _assert_no_residue(saved)

def test_file_txn_storage_io_error_is_translated_into_the_typed_hierarchy(
        lifecycle: StorageLifecycle, python_source: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """KNOWN WART, pinned deliberately: ``file_txn`` defines its OWN module-local
    ``StorageIOError``, a different class from ``exceptions.StorageIOError`` and
    no part of the typed hierarchy. The lifecycle translates it, so a caller sees
    only typed exceptions with ``phase``/``path`` kept in ``details``. If that
    shadowing is ever cleaned up, THIS behaviour must survive the cleanup."""
    assert file_txn_module.StorageIOError is not StorageIOError
    assert not issubclass(file_txn_module.StorageIOError, TreeEngineException)
    opened = lifecycle.open(python_source)
    _crash_between_publish_renames(monkeypatch, {python_source, opened.tree_path})
    with pytest.raises(StorageIOError) as info:
        lifecycle.save(opened)
    monkeypatch.undo()
    raised = info.value
    assert isinstance(raised, TreeEngineException)
    assert not isinstance(raised, file_txn_module.StorageIOError)
    assert raised.code is ErrorCode.STORAGE_IO_ERROR
    assert raised.details["phase"] == "publish_rename"
    assert raised.details["path"] == str(opened.tree_path)
    assert isinstance(raised.__cause__, file_txn_module.StorageIOError)
