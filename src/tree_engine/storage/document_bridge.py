"""The join between the stored source/tree pair and the MUTABLE working tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the one seam the storage layer and the mutation layer never had. ``storage/lifecycle.py``
and ``storage/codec.py`` speak the IMMUTABLE ``core.nodes.Document``; every mutating operation --
and therefore every facade command -- speaks the MUTABLE ``core.live_tree.TreeDocument``. With no
converter between them the facade's ``load``/``save`` could not route through storage at all, which
is why their docstrings said so verbatim, and why node identity was not in fact persisted anywhere:
a reopened document reparsed its source and ``reindex()`` minted a brand-new short_id map. Identity
that is not persisted is not identity. This module supplies both directions --
:func:`to_tree_document`, :func:`to_frozen_document` -- and SEEDS the live document's
``short_id_map`` from the stored one, which is the whole point: without the seed the reload keeps
the ``node_id`` and loses the ``short_id``, and the frozen editor API addresses nodes by short_id.

**The open decision, and why it is four branches and not two.** The owner's rule is that on OPEN
the source file is the truth and on WRITE the tree is; on reopen the recorded ``source_sha256``
decides between them. But a mismatch means two different things depending on one fact this layer
cannot know -- whether some session currently holds the file open. Before a file is opened the
bytes on disk are the truth and a mismatch means reparse with fresh identity; while a session holds
it the tree is the truth and the same mismatch means keep the stored tree, because the source on
disk is the stale one. So :class:`OpenBranch` carries all four cases under the names the editor's
own ``sha_sync_policy.ShaSyncBranch`` already uses for them (its "sidecar" is this engine's tree
file), and ``active_session_holds_file`` is a caller-supplied fact: the engine has no session
registry and must not grow one.

**What an open may and may not write.** The SOURCE file is immutable here: an open never rewrites
it, never repairs it and never normalises it, and it is not even part of the file transaction that
an open performs. The TREE file is a derived artefact and is persisted: created when absent,
refreshed when it disagrees with the source. That is not a violation of a read-only open, it is
what makes one useful -- a preview that reparses from scratch every time has no identity to hand
out and no history to record. :meth:`DocumentStore.open_file` therefore acts on the intent it
computes, while :meth:`DocumentStore.open_bytes` -- which holds content and no paths -- computes
the same intent, hands back the exact bytes to write, and touches no filesystem at all. Either way
the intent is reported, because the caller must know which paths changed in order to checkpoint
them, and :class:`WrittenPair` reports the same for a write.

**History.** Recording a document's history is part of this engine's lifecycle, not a favour a
consumer does afterwards: a checkpoint is taken when a document is opened and after every write,
by this module, through the :mod:`tree_engine.storage.history` port. The port is all the engine
knows -- it never creates or locates a store of any kind, and this module names no version-control
system. A consumer that supplies no port simply has no history recorded.

Source-of-truth labels honored here: {p085}-{p094}, {p097}, {p100}.
"""

from __future__ import annotations

from dataclasses import dataclass, replace as _replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple, Union

from tree_engine.core.live_tree import TreeDocument, to_frozen, to_live
from tree_engine.core.nodes import Document
from tree_engine.exceptions import StorageIOError, TreeEngineException
from tree_engine.plugins.fallback import PLAIN_TEXT_FORMAT_ID
from tree_engine.storage.codec import DecodedTreeFile
from tree_engine.storage.history import Checkpoint, CheckpointKind, HistoryPort
from tree_engine.storage.lifecycle import StorageLifecycle, canonical_tree_payload
from tree_engine.storage.session_guard import source_sha256, tree_payload_sha256

__all__ = ["FALLBACK_DIAGNOSTIC_KEY", "DocumentStore", "OpenBranch", "OpenedTree",
           "TreeWriteIntent", "WrittenPair", "to_frozen_document", "to_tree_document"]

#: Envelope ``format_metadata`` key under which the plain-text fallback's structured diagnostic is
#: persisted. The fallback is a property of the REPRESENTATION, not of the tree, so the envelope is
#: where it belongs; without it a document that degraded to plain text would come back from its own
#: tree file unable to say why it is not in its source format.
FALLBACK_DIAGNOSTIC_KEY = "fallback_diagnostic"


class OpenBranch(str, Enum):
    """Which of the four open cases the checksum decision landed in.

    The names are the editor's (``ai_editor.commands.universal_file_edit.sha_sync_policy``), so the
    two implementations of one rule are readably the same rule. ``NO_SIDECAR`` covers an absent
    tree file AND one no gate would accept -- undecodable, structurally invalid, or written by a
    plugin version this build does not have -- because in both cases there is no usable stored tree
    and the source is all there is; :attr:`OpenedTree.refusal` says which it was.
    """

    NO_SIDECAR = "no_sidecar"
    SHA_MATCH = "sha_match"
    SHA_MISMATCH_NO_SESSION = "sha_mismatch_no_session"
    SHA_MISMATCH_ACTIVE_SESSION = "sha_mismatch_active_session"


class TreeWriteIntent(str, Enum):
    """What has to happen to the tree file for it to describe the document just opened.

    ``CREATE`` when there was no usable tree file, ``REPLACE`` when there was one and the source
    superseded it, ``NONE`` when the stored tree IS the document or when no tree file can be
    produced for this format at all. :meth:`DocumentStore.open_file` acts on it; the byte-level
    open reports it and leaves the acting to a caller that owns the paths."""

    NONE = "none"
    CREATE = "create"
    REPLACE = "replace"


@dataclass(frozen=True)
class OpenedTree:
    """One open, its evidence, and the derived artefact it produced.

    ``identity_preserved`` is the single fact a caller most often needs: True when every node came
    back with the ``node_id`` AND ``short_id`` it was issued before, False when the tree was rebuilt
    from source and identity is fresh. It is exactly ``branch`` in {SHA_MATCH,
    SHA_MISMATCH_ACTIVE_SESSION}, restated as a boolean so no caller has to re-derive the rule.

    ``tree_bytes`` are the serialized tree file for this document -- the stored bytes when they
    were accepted, freshly encoded ones when the tree was rebuilt -- so a byte-level caller can act
    on ``tree_write_intent`` without re-deriving anything. It is None only when no tree file can be
    produced, and then ``tree_unavailable`` says why and the intent is ``NONE``: an intent that
    cannot be acted on would be a lie. ``written_paths`` is what THIS call wrote, which is the
    tree file or nothing, and never the source. ``refusal`` says why a supplied tree file was not
    used, and is None when none was supplied or when it was accepted."""

    document: TreeDocument
    branch: OpenBranch
    identity_preserved: bool
    tree_write_intent: TreeWriteIntent
    source_sha256: str
    stored_source_sha256: Optional[str] = None
    tree_path: Optional[Path] = None
    tree_bytes: Optional[bytes] = None
    tree_unavailable: Optional[str] = None
    written_paths: Tuple[Path, ...] = ()
    refusal: Optional[str] = None
    checkpoint_id: Optional[str] = None


@dataclass(frozen=True)
class WrittenPair:
    """What one write actually put on disk, for a caller that has to stage it.

    ``written_paths`` is the whole of the change, in publication order -- the source file and, for
    a format whose plugin implements the storage half of the plugin contract, its tree file. On
    success the file transaction leaves no journal, backup or temp file behind, so there is nothing
    else to stage. ``tree_path``/``tree_bytes``/``tree_payload_sha256`` are None only for a format
    plugin that cannot render a document into the storage layer, in which case identity was not
    persisted at all and the source file was written alone."""

    source_path: Path
    tree_path: Optional[Path]
    written_paths: Tuple[Path, ...]
    source_bytes: bytes
    source_sha256: str
    tree_bytes: Optional[bytes] = None
    tree_payload_sha256: Optional[str] = None
    checkpoint_id: Optional[str] = None


def _records_a_fallback(decoded: Optional[DecodedTreeFile]) -> bool:
    """True when a stored tree holds the degraded plain-text representation of another format
    ({p088}) -- the thing ``allow_plain_text_fallback=False`` refuses to be given."""
    return (decoded is not None
            and decoded.document.format_id == PLAIN_TEXT_FORMAT_ID
            and decoded.document.source_format_id != PLAIN_TEXT_FORMAT_ID)


def to_tree_document(decoded: DecodedTreeFile, source_bytes: bytes, *,
                     path: Optional[Path] = None) -> TreeDocument:
    """Rebuild the mutable working document from an accepted tree file, identity intact.

    The stored ``short_id_map`` is SEEDED into the live document rather than rebuilt: it is what
    tells ``reindex()`` that a node already owns short_id 7, and it carries the monotonic
    ``next_short_id`` above every value ever issued, so a short_id freed by an earlier delete is
    still never reused across the reload ({p097}). The envelope's ``document_id`` is carried too,
    so a persisted cross-document reference and a ``"document_id:node_id"`` address still resolve
    after a reopen, and the fallback diagnostic is restored from ``format_metadata`` so a degraded
    document still knows why it is degraded."""
    diagnostic = decoded.envelope.format_metadata.get(FALLBACK_DIAGNOSTIC_KEY)
    document = TreeDocument(
        to_live(decoded.document.root), decoded.document.source_format_id,
        decoded.document.format_id, source_bytes, path=path,
        fallback_diagnostic=diagnostic if isinstance(diagnostic, Mapping) else None,
        short_id_map=decoded.short_id_map)
    document.document_id = decoded.envelope.document_id
    return document


def to_frozen_document(document: TreeDocument) -> Document:
    """The immutable ``core.nodes.Document`` the storage layer and the codec render and encode.

    The inverse of :func:`to_tree_document` for everything storage reads: the node graph through
    ``to_frozen`` (which carries each node's ``node_id`` and ``short_id`` across unchanged, so the
    encoder's map is the live one), both format ids, and the ``document_id`` -- which is what makes
    a save/reload keep the same document identity instead of minting one per open."""
    frozen = Document(root=to_frozen(document.root), source_format_id=document.source_format_id,
                      representation_format_id=document.format_id)
    frozen.document_id = document.document_id
    return frozen


class DocumentStore:
    """The facade's storage half: open a document from bytes or from a path, and write the pair.

    Constructed once with the registry the facade itself resolves plugins through, so a format
    registered with the facade is immediately storable. ``parse_source`` is the facade's own
    ``loads`` and ``render_source`` its ``dumps``, injected rather than imported so this module
    stays below the facade in the import order; going through them also means the rebuild branch
    keeps the facade's own plugin resolution and its single authorized plain-text fallback instead
    of a second copy of either. ``history`` is the default :class:`HistoryPort` for every call, and
    any call may override it; with none, nothing is recorded.
    """

    def __init__(self, registry: Any, *, parse_source: Callable[..., TreeDocument],
                 render_source: Callable[[TreeDocument], bytes],
                 extension_table: Optional[Mapping[str, str]] = None,
                 lifecycle: Optional[StorageLifecycle] = None,
                 history: Optional[HistoryPort] = None) -> None:
        self._registry = registry
        self._parse_source = parse_source
        self._render_source = render_source
        self._history = history
        self._lifecycle = (StorageLifecycle(registry, extension_table=extension_table)
                           if lifecycle is None else lifecycle)

    @property
    def lifecycle(self) -> StorageLifecycle:
        """The storage lifecycle this store drives, for a caller that needs the pair's paths."""
        return self._lifecycle

    def tree_path_for(self, source_path: Union[str, Path]) -> Path:
        """Where the tree file for ``source_path`` lives ({p085})."""
        return self._lifecycle.tree_path_for(source_path)

    def open_bytes(self, source: Union[str, bytes], *, tree: Optional[bytes] = None,
                   format_id: Optional[str] = None, file_path: Optional[str] = None,
                   allow_plain_text_fallback: bool = True,
                   active_session_holds_file: bool = False,
                   history: Optional[HistoryPort] = None,
                   path: Optional[Path] = None) -> OpenedTree:
        """Decide the open from bytes alone: source bytes, and the stored tree file's bytes when
        the caller has them. Pure with respect to the filesystem -- it reads nothing and writes
        nothing -- so it is the entry point for a consumer that fetched both files from somewhere
        else entirely, and for one that must not create files where they live. The tree file the
        decision calls for is returned as bytes, for that caller to persist as it sees fit."""
        outcome = self._decide(source, tree, format_id, file_path, allow_plain_text_fallback,
                               active_session_holds_file, path)
        return self._checkpointed(outcome, CheckpointKind.OPEN, history)

    def open_file(self, path: Union[str, Path], *, format_id: Optional[str] = None,
                  allow_plain_text_fallback: bool = True,
                  active_session_holds_file: bool = False,
                  history: Optional[HistoryPort] = None) -> OpenedTree:
        """:meth:`open_bytes` over a real pair on disk, acting on the intent it computes.

        The source file is READ and never written: it takes no part in the file transaction this
        performs, so its bytes and its mtime are the same afterwards whatever the decision was. The
        derived tree file is created when there is none and refreshed when the source has
        superseded it, which is what gives the next open identity to hand out and this one a full
        checkpoint to record. An unreadable source is a typed ``StorageIOError``; an unreadable
        tree file is simply no tree file, which is the rebuild branch."""
        source = Path(path)
        try:
            source_bytes = source.read_bytes()
        except OSError as exc:
            raise StorageIOError(f"cannot read {source}: {exc}", path=str(source),
                                 phase="read") from exc
        try:
            tree_bytes: Optional[bytes] = self.tree_path_for(source).read_bytes()
        except OSError:
            tree_bytes = None
        outcome = self._decide(source_bytes, tree_bytes, format_id, str(source),
                               allow_plain_text_fallback, active_session_holds_file, source)
        if outcome.tree_write_intent is not TreeWriteIntent.NONE and outcome.tree_bytes is not None:
            written = self._lifecycle.publish_tree_only(source, outcome.tree_bytes)
            outcome = _replace(outcome, written_paths=(written,))
        return self._checkpointed(outcome, CheckpointKind.OPEN, history)

    def write(self, document: TreeDocument, path: Optional[Union[str, Path]] = None, *,
              history: Optional[HistoryPort] = None) -> WrittenPair:
        """Render ``document`` and publish the source/tree pair, reporting every path written.

        This is where identity is persisted through an edit: the tree file carries each node's
        ``node_id``/``short_id`` and the live ``short_id_map`` with its monotonic counter, so the
        next open of these bytes takes the SHA_MATCH branch and every surviving node keeps both
        identifiers. A format plugin that does not implement the storage half of the plugin
        contract -- ``render_document``, the marker of ``core.plugin_boundary.FormatBoundary`` --
        cannot be encoded into a tree file at all; its source is published alone and the returned
        ``tree_path`` is None, so a caller is told plainly that identity was not persisted rather
        than being left to assume it was. A checkpoint is recorded once the publication has been
        verified on disk, never before."""
        target = Path(path) if path is not None else document.path
        if target is None:
            raise StorageIOError("save() needs a path: this document came from loads(), not a file")
        plugin = self._registry.get_format_plugin(document.format_id)
        if not callable(getattr(plugin, "render_document", None)):
            content = self._render_source(document)
            self._lifecycle.publish_source_only(target, content)
            document.path, document.source_bytes = target, content
            pair = WrittenPair(source_path=target, tree_path=None, written_paths=(target,),
                               source_bytes=content, source_sha256=source_sha256(content))
            return _replace(pair, checkpoint_id=self._record(
                CheckpointKind.WRITE, document, pair.source_bytes, pair.source_sha256,
                tree_path=None, tree_bytes=None, written_paths=pair.written_paths, branch=None,
                history=history))
        published = self._lifecycle.publish_pair(
            target, to_frozen_document(document), short_id_map=document.short_id_map,
            format_metadata=self._format_metadata(document),
            document_version=document.document_version)
        document.path, document.source_bytes = published.source_path, published.source_bytes
        pair = WrittenPair(
            source_path=published.source_path, tree_path=published.tree_path,
            written_paths=published.written_paths, source_bytes=published.source_bytes,
            source_sha256=published.source_sha256, tree_bytes=published.tree_bytes,
            tree_payload_sha256=published.tree_payload_sha256)
        return _replace(pair, checkpoint_id=self._record(
            CheckpointKind.WRITE, document, pair.source_bytes, pair.source_sha256,
            tree_path=pair.tree_path, tree_bytes=pair.tree_bytes,
            written_paths=pair.written_paths, branch=None, history=history))

    # -- the decision itself ----------------------------------------------------

    def _decide(self, source: Union[str, bytes], tree: Optional[bytes], format_id: Optional[str],
                file_path: Optional[str], allow_plain_text_fallback: bool,
                active_session_holds_file: bool, path: Optional[Path]) -> OpenedTree:
        """The four-branch checksum decision, with no checkpoint and no write."""
        source_bytes = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        digest = source_sha256(source_bytes)
        tree_path = None if path is None else self.tree_path_for(path)
        if tree is None:
            return self._rebuilt(source_bytes, digest, OpenBranch.NO_SIDECAR,
                                 TreeWriteIntent.CREATE, format_id, file_path,
                                 allow_plain_text_fallback, path, tree_path, None, None)
        acceptance = self._lifecycle.accept_tree_bytes(tree, digest, tree_path=tree_path)
        if not allow_plain_text_fallback and _records_a_fallback(acceptance.stored):
            # A caller that declined the degraded representation must not be handed one out of
            # storage either: the stored tree IS a plain-text fallback of another format, so
            # accepting it would answer "no fallback" with a fallback.
            acceptance = _replace(
                acceptance, decoded=None, stored=None,
                refusal=f"stored tree file{'' if tree_path is None else f' {tree_path}'} holds "
                        "the plain-text fallback representation, which this call declined")
        if acceptance.decoded is not None:
            return OpenedTree(
                document=to_tree_document(acceptance.decoded, source_bytes, path=path),
                branch=OpenBranch.SHA_MATCH, identity_preserved=True,
                tree_write_intent=TreeWriteIntent.NONE, source_sha256=digest,
                stored_source_sha256=acceptance.stored_source_sha256, tree_path=tree_path,
                tree_bytes=tree)
        if acceptance.stored is not None and active_session_holds_file:
            # The tree is the truth here, so the document's source bytes are the ones the TREE
            # renders to -- not the stale bytes on disk, whose offsets would misaddress every
            # cached source slice.
            stored = acceptance.stored
            return OpenedTree(
                document=to_tree_document(stored, self._render_stored(stored), path=path),
                branch=OpenBranch.SHA_MISMATCH_ACTIVE_SESSION, identity_preserved=True,
                tree_write_intent=TreeWriteIntent.NONE, source_sha256=digest,
                stored_source_sha256=acceptance.stored_source_sha256, tree_path=tree_path,
                tree_bytes=tree, refusal=acceptance.refusal)
        branch = (OpenBranch.SHA_MISMATCH_NO_SESSION if acceptance.stored is not None
                  else OpenBranch.NO_SIDECAR)
        return self._rebuilt(source_bytes, digest, branch, TreeWriteIntent.REPLACE, format_id,
                             file_path, allow_plain_text_fallback, path, tree_path,
                             acceptance.stored_source_sha256, acceptance.refusal)

    def _rebuilt(self, source_bytes: bytes, digest: str, branch: OpenBranch,
                 intent: TreeWriteIntent, format_id: Optional[str], file_path: Optional[str],
                 allow_plain_text_fallback: bool, path: Optional[Path],
                 tree_path: Optional[Path], stored_digest: Optional[str],
                 refusal: Optional[str]) -> OpenedTree:
        """The rebuild branch: parse the source with fresh identity, then serialize the tree file
        that would record it -- against the digest of the source bytes exactly as given, because
        the source is not ours to rewrite."""
        document = self._parse_source(source_bytes, format_id=format_id, file_path=file_path,
                                      allow_plain_text_fallback=allow_plain_text_fallback)
        if path is not None:
            document.path = path
        tree_bytes, unavailable = self._tree_artefact(document, source_bytes)
        return OpenedTree(document=document, branch=branch, identity_preserved=False,
                          tree_write_intent=intent if tree_bytes is not None
                          else TreeWriteIntent.NONE,
                          source_sha256=digest, stored_source_sha256=stored_digest,
                          tree_path=tree_path, tree_bytes=tree_bytes,
                          tree_unavailable=unavailable, refusal=refusal)

    def _tree_artefact(self, document: TreeDocument,
                       source_bytes: bytes) -> Tuple[Optional[bytes], Optional[str]]:
        """The tree file bytes for a freshly parsed document, or the reason there are none.

        The render check is the one gate an open owes that a write does not: a write publishes the
        source from the same render, so the two agree by construction, while an open must leave the
        source alone and record the tree against the digest of bytes it did not produce. If the
        format's round trip does not reproduce those bytes -- a known-weak generator, an
        unrepresentable construct -- then a tree stored under that digest would be accepted on the
        next open and would hand back a document that is not the file. Refusing to produce it costs
        one render and prevents silently substituting the wrong content."""
        plugin = self._registry.get_format_plugin(document.format_id)
        if not callable(getattr(plugin, "render_document", None)):
            return None, (f"the {document.format_id!r} plugin does not implement the storage half "
                          "of the plugin contract, so it has no tree file and node identity "
                          "cannot be persisted for this format")
        try:
            rendered = self._render_source(document)
        except TreeEngineException as exc:
            return None, f"the parsed tree does not render back to source: {exc}"
        if rendered != source_bytes:
            return None, (f"the {document.format_id!r} round trip does not reproduce the source "
                          "bytes, so a tree file recorded against their checksum would not "
                          "describe this file")
        try:
            return self._lifecycle.encode_tree(
                to_frozen_document(document), source_bytes,
                short_id_map=document.short_id_map,
                format_metadata=self._format_metadata(document),
                document_version=document.document_version), None
        except TreeEngineException as exc:
            return None, f"the parsed tree cannot be serialized: {exc}"

    def _format_metadata(self, document: TreeDocument) -> Mapping[str, Any]:
        """Envelope metadata for this document: its fallback diagnostic, when it has one."""
        return ({} if document.fallback_diagnostic is None
                else {FALLBACK_DIAGNOSTIC_KEY: dict(document.fallback_diagnostic)})

    def _render_stored(self, stored: DecodedTreeFile) -> bytes:
        """The source bytes a stored tree renders to, through its own representation plugin."""
        plugin = self._registry.get_format_plugin(stored.document.format_id)
        rendered = plugin.render_document(stored.document)
        return rendered if isinstance(rendered, bytes) else str(rendered).encode("utf-8")

    # -- history ----------------------------------------------------------------

    def _checkpointed(self, outcome: OpenedTree, kind: CheckpointKind,
                      history: Optional[HistoryPort]) -> OpenedTree:
        """Record the open checkpoint, if a port was supplied, and carry back its revision."""
        return _replace(outcome, checkpoint_id=self._record(
            kind, outcome.document, outcome.document.source_bytes, outcome.source_sha256,
            tree_path=outcome.tree_path, tree_bytes=outcome.tree_bytes,
            written_paths=outcome.written_paths, branch=outcome.branch.value, history=history))

    def _record(self, kind: CheckpointKind, document: TreeDocument, source_bytes: bytes,
                digest: str, *, tree_path: Optional[Path], tree_bytes: Optional[bytes],
                written_paths: Tuple[Path, ...], branch: Optional[str],
                history: Optional[HistoryPort]) -> Optional[str]:
        """Invoke the history port for one checkpoint. The engine calls this; a consumer never
        does. With no port supplied there is no history and nothing happens."""
        port = self._history if history is None else history
        if port is None:
            return None
        return port.record_checkpoint(Checkpoint(
            kind=kind, document_id=document.document_id,
            document_version=document.document_version, source_path=document.path,
            source_bytes=source_bytes, source_sha256=digest, tree_path=tree_path,
            tree_bytes=tree_bytes,
            tree_payload_sha256=None if tree_bytes is None
            else tree_payload_sha256(canonical_tree_payload(tree_bytes)),
            written_paths=written_paths, branch=branch, format_id=document.format_id,
            source_format_id=document.source_format_id))
