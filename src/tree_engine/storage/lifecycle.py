"""Storage lifecycle orchestrator for the source/tree file pair (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Per {p085}-{p094}: the only place that owns a *pair* of files -- a source
document and the tree file beside it -- as an open/save/reparse lifecycle, and it
orchestrates rather than reimplements. ``schema``/``codec`` own the envelope, the
version gate and ``tree_payload_sha256``; ``session_guard`` owns both digests and
every external-modification verdict ({p089}); ``file_txn`` owns recoverable
publication ({p090}); ``validate_full_document`` owns the structural verdict
({p092}); ``plugins.selection``/``registry``/``fallback`` resolve the plugin and
build the degraded tree ({p088}).

Open gates, in order ({p087}): journal recovery, source read, plugin resolution,
then a stored tree is accepted *without* ``parse_document`` only when
envelope/schema decoding, both SHAs, the plugin's availability and contract
compatibility, and full structural validation all pass. Two failures are raised
rather than rebuilt away, because they say the file came from an environment this
build cannot interpret: an unknown major schema (``TREE_SCHEMA_UNSUPPORTED``,
{p100}) and an absent or contract-incompatible plugin
(``FORMAT_PLUGIN_NOT_FOUND``/``FORMAT_PLUGIN_CONTRACT_ERROR``, never a fallback).
Everything else -- missing, corrupt or checksum-stale tree file, a compatible
plugin *version* change -- takes {p088}'s rebuild branch, which
:meth:`StorageLifecycle.reparse` also forces: parse (or, only on
``FORMAT_CONTENT_PARSE_FAILED``, the fallback) -> encode -> atomic publication ->
reread -> that same branch, so no unvalidated in-memory tree is ever returned
({p094}). Paths, digests, baselines and recovery reports live on
:class:`OpenedDocument`/``EditSession``, never on the tree ({p025}, {p093}).

Source-of-truth labels: {p006}, {p007}, {p025}, {p037}, {p052}, {p085}-{p094}, {p100}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple, Union

from tree_engine.core.integrity_full import FullIntegrityError, validate_full_document
from tree_engine.core.nodes import Document, Node
from tree_engine.core.reference_cache import ReferenceIndex
from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (
    ChecksumMismatch, StorageIOError, TreeEngineException, TreePayloadInvalid,
    TreeSchemaUnsupported, exception_for_code)
from tree_engine.plugins.fallback import PLAIN_TEXT_FORMAT_ID, build_fallback_tree
from tree_engine.plugins.selection import build_extension_table, resolve_format_plugin
from tree_engine.storage.codec import (
    DecodedTreeFile, canonical_bytes, decode, encode, short_id_map_for)
from tree_engine.storage.file_txn import FileWrite, RecoveryReport, publish, recover
from tree_engine.storage.schema import TreeFile, TreeFileEnvelope, TreeFileSchemaError
from tree_engine.storage.session_guard import (
    ConflictResolutionPolicy, EditSession, source_sha256, tree_payload_sha256)

__all__ = ["DEFAULT_TREE_SUFFIX", "DEFAULT_JOURNAL_SUFFIX", "OpenedDocument", "PublishedPair",
           "StorageLifecycle", "TreeAcceptance", "canonical_tree_payload", "validate_structure"]

PathLike = Union[str, Path]

#: Appended to the source file's own name, so the pair is discoverable from
#: either side and two documents in one directory never collide.
DEFAULT_TREE_SUFFIX = ".tree.json"

#: The pair's file-transaction journal; its presence at open time is the single
#: fact that says a publication was interrupted ({p090}).
DEFAULT_JOURNAL_SUFFIX = ".storage-journal"

def canonical_tree_payload(raw_tree_file_bytes: bytes) -> bytes:
    """Canonical payload bytes of a tree file, for the session guard's digest.
    Pins :class:`EditSession` to the canonicalization ``codec`` itself uses, so a
    session baseline and a tree file's ``CHECKSUMS`` entry are the same number
    ({p086}); anything undecodable is ``TreePayloadInvalid``."""
    try:
        data = json.loads(raw_tree_file_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TreePayloadInvalid(f"tree file is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise TreePayloadInvalid(f"tree file must be a JSON object, got {type(data).__name__}")
    try:
        tree_file = TreeFile.from_dict(data)
    except TreeFileSchemaError as exc:
        raise TreePayloadInvalid(str(exc)) from exc
    return canonical_bytes(tree_file.payload.to_dict())

@dataclass(frozen=True)
class _DocumentView:
    """The duck-typed shape :func:`validate_full_document` documents."""
    root: Node
    reference_index: ReferenceIndex

def validate_structure(document: Document) -> None:
    """Run the core's full structural validation over ``document`` ({p092}).
    Projects the node graph onto a fresh :class:`ReferenceIndex` -- parent/child
    from ``children``, short_ids from each node's own ``short_id``, outgoing edges
    from ``references`` -- for :func:`validate_full_document`, which owns every
    actual check. A node with no ``node_id`` is unindexable and skipped, as that
    validator also skips it; a violation is ``TREE_PAYLOAD_INVALID``."""
    index = ReferenceIndex()
    edges: List[Tuple[Any, Sequence[Any]]] = []
    stack: List[Tuple[Node, Any]] = [(document.root, None)]
    try:
        while stack:
            node, parent_id = stack.pop()
            node_id = node.node_id
            if node_id is not None:
                index.register_node(node_id, node, parent_id=parent_id, short_id=node.short_id)
                if node.references:
                    edges.append((node_id, node.references))
            for child in node.children:
                stack.append((child, node_id if node_id is not None else parent_id))
        for node_id, references in edges:
            index.update_references(node_id, (), references)
    except (ValueError, TypeError, AttributeError) as exc:
        raise TreePayloadInvalid(f"tree structure cannot be indexed: {exc}") from exc
    try:
        validate_full_document(_DocumentView(document.root, index))
    except FullIntegrityError as exc:
        raise TreePayloadInvalid(f"tree structure is invalid: {exc}") from exc

@dataclass(frozen=True)
class OpenedDocument:
    """One open document: the tree plus every file fact the tree must not hold.
    ``document``/``short_id_map``/``envelope`` come off the accepted tree file,
    ``session`` guards the accepted digests, ``rebuilt`` says the tree file was
    rewritten here, ``fallback`` that the representation is the degraded plain-text
    one, ``recovery`` what an interrupted publication left -- storage state, never
    on ``document`` ({p025}, {p088}, {p090}, {p093})."""
    document: Document
    short_id_map: ShortIdMap
    envelope: TreeFileEnvelope
    source_path: Path
    tree_path: Path
    journal_path: Path
    session: EditSession
    source_sha256: str
    tree_payload_sha256: str
    format_id: str
    rebuilt: bool
    fallback: bool
    recovery: RecoveryReport

@dataclass(frozen=True)
class TreeAcceptance:
    """Everything the {p087} gates establish about one tree file's bytes.

    ``decoded`` is the tree file when EVERY gate passed, including that it records
    this exact source -- the only case in which it may be used as the document.
    ``stored`` is the tree file when every gate except that one passed: a usable
    tree that describes DIFFERENT source bytes. The two are distinguished because
    which of them wins is not storage's decision to take: before a file is open
    the file is the truth and a mismatch means reparse, but while a session holds
    it the tree is the truth and the same mismatch means keep the tree. Only the
    caller knows which of those it is in. ``stored_source_sha256`` is the digest
    the file records, present whenever it decoded at all, and ``refusal`` names
    the gate that refused it, so "rebuilt" is never reported without a reason."""
    decoded: Optional[DecodedTreeFile]
    stored: Optional[DecodedTreeFile]
    stored_source_sha256: Optional[str]
    refusal: Optional[str]


@dataclass(frozen=True)
class PublishedPair:
    """What one publication of the source/tree pair actually put on disk.

    ``written_paths`` is the exact set of files this call created or replaced,
    in publication order -- the output a caller needs to STAGE the result
    somewhere else (the editor commits them to its own per-session git repo)
    without having to reconstruct the tree-file naming convention. On success
    ``file_txn.publish`` leaves no journal, backup or temp file behind, so these
    paths are the whole of the change. ``source_bytes`` are the bytes written to
    ``source_path`` and the two digests are the ones recorded in the tree file,
    so a caller never has to re-read a file to learn what it now holds."""
    source_path: Path
    tree_path: Path
    written_paths: Tuple[Path, ...]
    source_bytes: bytes
    tree_bytes: bytes
    source_sha256: str
    tree_payload_sha256: str
    envelope: TreeFileEnvelope


def _code_of(exc: BaseException) -> Optional[ErrorCode]:
    """The catalog code an exception carries, under either the typed
    hierarchy's ``code`` or the plugin/registry/selection ``error_code``."""
    for attribute in ("code", "error_code"):
        candidate = getattr(exc, attribute, None)
        if isinstance(candidate, ErrorCode):
            return candidate
    return None

def _typed(exc: BaseException) -> BaseException:
    """Map a neighbouring layer's error onto the typed hierarchy by its code.
    Already-typed errors pass through; everything else becomes the class
    :func:`exception_for_code` fixes, so a caller sees only
    ``tree_engine.exceptions`` types and ``file_txn``'s own same-named
    ``StorageIOError`` arrives as the catalog's, ``phase``/``path`` kept."""
    if isinstance(exc, TreeEngineException):
        return exc
    code = _code_of(exc)
    if code is None:
        return exc
    details = {name: str(value) for name, value in (
        ("path", getattr(exc, "path", None)), ("phase", getattr(exc, "phase", None)),
        ("plugin_id", getattr(exc, "plugin_id", None))) if value is not None}
    return exception_for_code(code)(str(exc), **details)

def _call(operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a neighbouring call, translating its error via :func:`_typed`."""
    try:
        return operation(*args, **kwargs)
    except TreeEngineException:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised as a catalog-typed error
        typed = _typed(exc)
        if typed is exc:
            raise
        raise typed from exc

def _is_fallback(envelope: TreeFileEnvelope) -> bool:
    """True for a plain-text representation of a non-plain-text document ({p088})."""
    return (envelope.representation_format_id == PLAIN_TEXT_FORMAT_ID
            and envelope.source_format_id != PLAIN_TEXT_FORMAT_ID)

class StorageLifecycle:
    """Open/save/reparse for the linked source-file and tree-file pair ({p085}).
    ``registry`` is any object exposing ``get_format_plugin(format_id)``, in
    practice ``plugins.registry.FormatPluginRegistry``; the extension table for
    path-based selection is rebuilt from its loaded plugins per call unless a
    fixed ``extension_table`` is given, as an entry-point-only deployment must."""
    def __init__(self, registry: Any, *, extension_table: Optional[Mapping[str, str]] = None,
                 tree_suffix: str = DEFAULT_TREE_SUFFIX,
                 journal_suffix: str = DEFAULT_JOURNAL_SUFFIX) -> None:
        self._registry = registry
        self._extension_table = extension_table
        self._tree_suffix = tree_suffix
        self._journal_suffix = journal_suffix

    def tree_path_for(self, source_path: PathLike) -> Path:
        """The serialized tree file paired with ``source_path`` ({p085})."""
        return Path(str(source_path) + self._tree_suffix)

    def journal_path_for(self, source_path: PathLike) -> Path:
        """The file-transaction journal for this pair ({p090})."""
        return Path(str(source_path) + self._journal_suffix)

    def open(self, source_path: PathLike, *, format_id: Optional[str] = None) -> OpenedDocument:
        """Open the pair, accepting a valid tree file without ``parse_document``.
        Recovers an interrupted publication first ({p090}), then runs the {p087}
        gates; a stale or damaged tree file falls through to {p088}'s rebuild.
        Raises ``TreeSchemaUnsupported``/``FormatPluginNotFound``/
        ``FormatPluginContractError`` for a file this build must not reinterpret."""
        return self._open(source_path, format_id, force_rebuild=False)

    def reparse(self, source_path: PathLike, *, format_id: Optional[str] = None) -> OpenedDocument:
        """Force the rebuild branch even over a fully valid tree file: {p037}'s
        explicit reparse -- parse (or fallback), encode, publish atomically,
        reread, revalidate through :meth:`open`'s own branch."""
        return self._open(source_path, format_id, force_rebuild=True)

    explicit_reparse = reparse  # {p037}'s spelling of the same operation

    def save(self, opened: OpenedDocument, document: Optional[Document] = None, *,
             policy: ConflictResolutionPolicy = ConflictResolutionPolicy.REFUSE,
             short_id_map: Optional[ShortIdMap] = None,
             format_metadata: Optional[Mapping[str, Any]] = None,
             ) -> OpenedDocument:
        """Publish the edited pair as one recoverable transaction ({p090}, {p091}).
        Validates the tree fully, renders source bytes and the canonical payload
        (neither touches disk), re-verifies both files against the session
        baselines -- refusing with ``CONCURRENT_SOURCE_MODIFICATION`` or
        ``CONCURRENT_TREE_MODIFICATION`` unless ``policy`` names the overwrite --
        publishes both atomically, rereads, re-verifies both digests, advances the
        baselines, then re-runs the acceptance branch; a post-publication mismatch
        runs recovery and is re-raised. ``short_id_map``/``format_metadata`` are
        carried through to :meth:`_encode`, which documents why a caller holding a
        live map must pass it."""
        target = opened.document if document is None else document
        validate_structure(target)
        plugin = self._plugin(target.representation_format_id)
        source_bytes = _call(plugin.render_document, target)
        digest = source_sha256(source_bytes)
        tree_bytes = self._encode(
            target, source_bytes, digest, plugin, document_id=opened.envelope.document_id,
            document_version=opened.envelope.document_version + 1,
            short_id_map=short_id_map, format_metadata=format_metadata)
        payload_digest = tree_payload_sha256(canonical_tree_payload(tree_bytes))
        opened.session.check_before_write(policy=policy)
        _call(publish, [FileWrite(opened.source_path, source_bytes),
                        FileWrite(opened.tree_path, tree_bytes)], opened.journal_path)
        try:
            opened.session.accept_publication(digest, payload_digest)
        except ChecksumMismatch:
            _call(recover, [opened.source_path, opened.tree_path], opened.journal_path)
            raise
        accepted = self._accept(opened.tree_path, digest, strict=True)
        return self._opened(
            accepted, opened.source_path, opened.tree_path, opened.journal_path,
            opened.session, digest, opened.format_id, rebuilt=False,
            fallback=_is_fallback(accepted.envelope), recovery=opened.recovery)

    def _open(self, source_path: PathLike, format_id: Optional[str], *,
              force_rebuild: bool) -> OpenedDocument:
        source = Path(source_path)
        tree = self.tree_path_for(source)
        journal = self.journal_path_for(source)
        recovery: RecoveryReport = _call(recover, [source, tree], journal)
        source_bytes = self._read(source)
        digest = source_sha256(source_bytes)
        plugin = self._resolve(source, format_id)
        fmt = plugin.metadata.format_id
        accepted = None if force_rebuild else self._accept(tree, digest)
        rebuilt = accepted is None
        fallback = False
        if rebuilt:
            fallback = self._rebuild(tree, journal, source_bytes, digest, plugin, fmt)
            accepted = self._accept(tree, digest, strict=True)
        session = EditSession(
            source, tree, base_source_sha256=digest,
            base_tree_payload_sha256=accepted.checksums.tree_payload_sha256,
            tree_canonicalizer=canonical_tree_payload)
        return self._opened(
            accepted, source, tree, journal, session, digest, fmt,
            rebuilt=rebuilt, fallback=fallback or _is_fallback(accepted.envelope),
            recovery=recovery)

    def accept_tree_bytes(self, tree_bytes: bytes, source_digest: str, *, strict: bool = False,
                          tree_path: Optional[Path] = None) -> TreeAcceptance:
        """The {p087} acceptance gates over tree-file BYTES, touching no disk.
        The decision half of :meth:`open`, exposed on its own so a caller holding
        both files' bytes -- an editor that fetched them from somewhere that is
        not this filesystem -- takes the same decision without a path, and takes
        it without writing anything. See :class:`TreeAcceptance` for what the four
        reported facts mean; gate order is exactly :meth:`open`'s, so a stale tree
        file is still reported stale before any plugin is asked about it. Raises,
        never rebuilds, for a file this build must not reinterpret (unknown major
        schema, and -- for a tree file that does record this source -- an absent or
        contract-incompatible plugin), and under ``strict``, the post-publication
        reread, for every other gate too."""
        label = f" {tree_path}" if tree_path is not None else ""
        try:
            decoded = decode(tree_bytes)
        except TreeSchemaUnsupported:
            raise
        except (TreePayloadInvalid, ChecksumMismatch) as exc:
            if strict:
                raise
            return TreeAcceptance(None, None, None, f"stored tree file{label} does not decode: {exc}")
        stored_digest = decoded.checksums.source_sha256
        if stored_digest != source_digest:
            if strict:
                raise ChecksumMismatch(
                    f"published tree file{label} records a stale source_sha256",
                    path=None if tree_path is None else str(tree_path),
                    expected_source_sha256=source_digest, actual_source_sha256=stored_digest)
            stale = (f"stored tree file{label} records source_sha256 {stored_digest}, "
                     f"the source hashes to {source_digest}")
            try:
                usable, refusal = self._plugin_and_structure_gates(decoded, label)
            except TreeEngineException as exc:
                return TreeAcceptance(None, None, stored_digest, f"{stale}, and {exc}")
            return TreeAcceptance(None, usable, stored_digest,
                                  stale if usable is not None else refusal)
        usable, refusal = self._plugin_and_structure_gates(decoded, label, strict=strict)
        if usable is None:
            return TreeAcceptance(None, None, stored_digest, refusal)
        return TreeAcceptance(decoded, decoded, stored_digest, None)

    def _plugin_and_structure_gates(self, decoded: DecodedTreeFile, label: str, *,
                                    strict: bool = False,
                                    ) -> Tuple[Optional[DecodedTreeFile], Optional[str]]:
        """The two {p087} gates that ask about the tree itself rather than about
        the source it records: the representation plugin must be installed and
        contract-compatible (raising, never rebuilding), at the version that wrote
        the file, and the node graph must pass full structural validation."""
        plugin = self._representation_plugin(decoded.envelope)
        if not strict and plugin.metadata.plugin_version != decoded.envelope.plugin_version:
            return None, (f"stored tree file{label} was written by {decoded.envelope.plugin_id} "
                          f"{decoded.envelope.plugin_version}, the installed plugin is "
                          f"{plugin.metadata.plugin_version}")
        try:
            validate_structure(decoded.document)
        except TreePayloadInvalid as exc:
            if strict:
                raise
            return None, f"stored tree file{label} fails structural validation: {exc}"
        return decoded, None

    def _accept(self, tree_path: Path, source_digest: str, *,
                strict: bool = False) -> Optional[DecodedTreeFile]:
        """:meth:`accept_tree_bytes` over the tree file at ``tree_path``; an
        absent file is the rebuild branch, or ``StorageIOError`` under ``strict``."""
        if not tree_path.exists():
            if strict:
                raise StorageIOError(f"published tree file {tree_path} is missing",
                                     path=str(tree_path), phase="reread")
            return None
        return self.accept_tree_bytes(self._read(tree_path), source_digest, strict=strict,
                                      tree_path=tree_path).decoded

    def _representation_plugin(self, envelope: TreeFileEnvelope) -> Any:
        """Plugin gate of {p087}: absent is ``FORMAT_PLUGIN_NOT_FOUND``, an
        incompatible ``contract_version`` major ``FORMAT_PLUGIN_CONTRACT_ERROR``;
        neither allows a fallback or a rebuild."""
        plugin = self._plugin(envelope.plugin_id)
        declared = plugin.metadata.contract_version
        if declared.split(".", 1)[0] != envelope.plugin_contract_version.split(".", 1)[0]:
            raise exception_for_code(ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR)(
                f"tree file declares plugin_contract_version "
                f"{envelope.plugin_contract_version!r}, but the installed "
                f"{envelope.plugin_id!r} plugin declares {declared!r}",
                plugin_id=envelope.plugin_id)
        return plugin

    def _rebuild(self, tree_path: Path, journal_path: Path, source_bytes: bytes,
                 digest: str, plugin: Any, format_id: str) -> bool:
        """Rebuild from source ({p088}) and publish the tree file atomically.
        Only a classified ``FORMAT_CONTENT_PARSE_FAILED`` opens the C-013
        sibling's fallback; any other diagnostic propagates."""
        document, fallback = self._parse(plugin, source_bytes, format_id)
        representation = self._plugin(PLAIN_TEXT_FORMAT_ID) if fallback else plugin
        validate_structure(document)
        tree_bytes = self._encode(document, source_bytes, digest, representation)
        _call(publish, [FileWrite(tree_path, tree_bytes)], journal_path)
        return fallback

    def _parse(self, plugin: Any, source_bytes: bytes, format_id: str) -> Tuple[Document, bool]:
        try:
            return plugin.parse_document(source_bytes, source_format_id=format_id), False
        except TreeEngineException as exc:
            # A typed error is already classified, but "already typed" must not
            # mean "never rescued": FormatContentParseFailed IS the fallback
            # trigger, and plugins split across two exception carriers. Keying
            # only on the older one left json/toml/yaml with no fallback at all.
            if _code_of(exc) is not ErrorCode.FORMAT_CONTENT_PARSE_FAILED:
                raise
            return build_fallback_tree(source_bytes, exc, source_format_id=format_id).document, True
        except Exception as exc:  # noqa: BLE001 - classified below, never swallowed
            if _code_of(exc) is not ErrorCode.FORMAT_CONTENT_PARSE_FAILED:
                typed = _typed(exc)
                if typed is exc:
                    raise
                raise typed from exc
            return build_fallback_tree(source_bytes, exc, source_format_id=format_id).document, True

    def _encode(self, document: Document, source_bytes: bytes, digest: str, plugin: Any,
                *, document_id: Optional[Any] = None, document_version: int = 0,
                short_id_map: Optional[ShortIdMap] = None,
                format_metadata: Optional[Mapping[str, Any]] = None) -> bytes:
        """Serialize through the codec with the plugin identity the gate checks
        and the ``source_sha256`` of these exact bytes ({p085}). ``short_id_map``
        is the caller's LIVE map when it has one: deriving the map from the
        document's own nodes recovers every issued short_id but not the monotonic
        ``next_short_id`` counter above them, so a value released by a delete
        would come back into circulation on the next reload -- the one thing
        {p097} forbids. ``format_metadata`` rides in the envelope for facts that
        belong to the representation rather than the tree, the plain-text
        fallback's diagnostic being the one this build carries."""
        metadata = plugin.metadata
        return _call(
            encode, document,
            short_id_map=short_id_map if short_id_map is not None else short_id_map_for(document),
            document_id=document_id, document_version=document_version,
            source_sha256=digest, plugin_id=metadata.format_id,
            plugin_version=metadata.plugin_version,
            plugin_contract_version=metadata.contract_version,
            trailing_newline=source_bytes.endswith(b"\n"),
            format_metadata=dict(format_metadata or {}))

    def publish_pair(self, source_path: PathLike, document: Document, *,
                     short_id_map: Optional[ShortIdMap] = None,
                     format_metadata: Optional[Mapping[str, Any]] = None,
                     document_version: int = 0) -> PublishedPair:
        """Render ``document`` and publish the source/tree pair at ``source_path``
        as one recoverable transaction ({p090}), reporting exactly what was
        written. The unsessioned counterpart of :meth:`save`: it takes no
        :class:`OpenedDocument` and checks no baseline, because it is the write a
        caller performs when IT -- not this layer -- owns the concurrency story
        (the editor holds the session and commits the result to its own git
        repository). Everything else is :meth:`save`'s discipline unchanged:
        structural validation first, both files published atomically, then the
        published tree file reread and revalidated through the same strict
        acceptance branch, so no unvalidated tree is ever reported as written."""
        source = Path(source_path)
        tree, journal = self.tree_path_for(source), self.journal_path_for(source)
        validate_structure(document)
        plugin = self._plugin(document.representation_format_id)
        source_bytes = _call(plugin.render_document, document)
        digest = source_sha256(source_bytes)
        tree_bytes = self._encode(document, source_bytes, digest, plugin,
                                  document_id=document.document_id,
                                  document_version=document_version,
                                  short_id_map=short_id_map, format_metadata=format_metadata)
        _call(publish, [FileWrite(source, source_bytes), FileWrite(tree, tree_bytes)], journal)
        accepted = self._accept(tree, digest, strict=True)
        return PublishedPair(
            source_path=source, tree_path=tree, written_paths=(source, tree),
            source_bytes=source_bytes, tree_bytes=tree_bytes, source_sha256=digest,
            tree_payload_sha256=accepted.checksums.tree_payload_sha256,
            envelope=accepted.envelope)

    def encode_tree(self, document: Document, source_bytes: bytes, *,
                    short_id_map: Optional[ShortIdMap] = None,
                    format_metadata: Optional[Mapping[str, Any]] = None,
                    document_version: int = 0) -> bytes:
        """Serialize the tree file for ``document`` over ``source_bytes``, writing NOTHING.

        The tree file is a DERIVED artefact of a source this call must not alter, so the
        ``source_sha256`` it records is the digest of ``source_bytes`` exactly as given -- never of
        a re-render of the document. That is what lets the next open of those untouched bytes take
        the checksum-match branch. It also means the caller owes one check before persisting the
        result: a document whose render does NOT reproduce ``source_bytes`` would be stored under a
        digest it does not correspond to, and reloading it would silently hand back a tree that is
        not the file. :meth:`publish_pair` has no such duty, because there the source is written
        from the same render."""
        validate_structure(document)
        plugin = self._plugin(document.representation_format_id)
        return self._encode(document, source_bytes, source_sha256(source_bytes), plugin,
                            document_id=document.document_id, document_version=document_version,
                            short_id_map=short_id_map, format_metadata=format_metadata)

    def publish_tree_only(self, source_path: PathLike, tree_bytes: bytes) -> Path:
        """Publish the derived tree file beside ``source_path`` and NOT the source itself.

        The source file is not in this transaction at all -- it is not read, not rewritten, not
        normalised -- which is the guarantee an open has to make: opening a document may bring its
        derived tree file into existence or up to date, and may never change the document. Returns
        the tree path written."""
        source = Path(source_path)
        tree = self.tree_path_for(source)
        _call(publish, [FileWrite(tree, tree_bytes)], self.journal_path_for(source))
        return tree

    def publish_source_only(self, source_path: PathLike, source_bytes: bytes) -> Path:
        """Publish the source file alone, with no tree file beside it ({p090}). The degraded write:
        for a format whose plugin cannot be encoded into a tree file there is no second artefact to
        publish, and writing one half of a pair is the honest outcome rather than a fabricated
        tree. Returns the source path written."""
        source = Path(source_path)
        _call(publish, [FileWrite(source, source_bytes)], self.journal_path_for(source))
        return source

    def _opened(self, accepted: DecodedTreeFile, source: Path, tree: Path, journal: Path,
                session: EditSession, digest: str, format_id: str, *, rebuilt: bool,
                fallback: bool, recovery: RecoveryReport) -> OpenedDocument:
        return OpenedDocument(
            document=accepted.document, short_id_map=accepted.short_id_map,
            envelope=accepted.envelope, source_path=source, tree_path=tree,
            journal_path=journal, session=session, source_sha256=digest,
            tree_payload_sha256=accepted.checksums.tree_payload_sha256,
            format_id=format_id, rebuilt=rebuilt, fallback=fallback, recovery=recovery)

    def _plugin(self, format_id: str) -> Any:
        return _call(self._registry.get_format_plugin, format_id)

    def _resolve(self, source: Path, format_id: Optional[str]) -> Any:
        table = self._extension_table
        if table is None:
            table = build_extension_table(_call(self._registry.list_format_plugins))
        return _call(resolve_format_plugin, format_id=format_id, file_path=str(source),
                     registry=self._registry, extension_table=table)

    def _read(self, path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageIOError(f"cannot read {path}: {exc}",
                                 path=str(path), phase="read") from exc
