"""Edit-session conflict guard with dual-SHA verification (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope (C-012, narrowed to this atomic step's target file), per {p086} and
{p089}: two coordinated things and nothing else.

1. Pure dual-SHA helpers. :func:`source_sha256` hashes the exact source
   bytes with no normalization at all -- no newline folding, no encoding
   round-trip, no trimming -- so the digest tracks the file byte-for-byte.
   :func:`tree_payload_sha256` hashes the codec layer's canonical tree
   payload with the CHECKSUMS section excluded, since that section holds
   the digest itself. Both are stateless module-level functions holding no
   reference to any tree object, reusable for acceptance gating at open and
   for post-publication verification alike.

2. :class:`EditSession`. At open it records ``base_source_sha256`` and
   ``base_tree_payload_sha256``; before any write it re-reads *both* files
   and recomputes both digests. A changed source raises
   ``ConcurrentSourceModification``, a changed tree file
   ``ConcurrentTreeModification``; :meth:`EditSession.accept_publication`
   advances the base digests once a publish is verified ({p091}).

Content, not metadata: per {p093} mtime and size are an auxiliary
optimization for this layer only, never a decision input. They ride on
:class:`FileEvidence` purely as diagnostics; every verdict comes from the
SHA-256 of the bytes, because a same-second edit that leaves the file the
same size is a real modification and must still be caught. A detected
conflict may be overwritten only by naming a
:class:`ConflictResolutionPolicy` member -- no boolean ``force`` flag
exists, and the default is ``REFUSE``.

Boundaries. All state here lives on the session, never on the tree object
({p025}, {p089}). In-process serialization belongs to
:class:`tree_engine.core.locking.DocumentLockCoordinator`; publication
belongs to :mod:`tree_engine.storage.file_txn`, which deliberately carries
no external-modification detection -- that duty is this module's. Two
concurrent sessions keep independent baselines and nothing is arbitrated
here: whichever publishes first and accepts stays consistent, while a
session still on the older baseline is refused at its next check -- first
publisher wins, later ones are refused, never merged ({p035}).

Source-of-truth labels honored here: {p086}, {p089}, {p091}, {p093}.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Union

from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (
    ChecksumMismatch,
    ConcurrentSourceModification,
    ConcurrentTreeModification,
    StorageIOError,
    TreePayloadInvalid,
)

__all__ = [
    "CHECKSUMS_SECTION_KEYS", "ConflictResolutionPolicy", "FileEvidence",
    "ConflictReport", "EditSession", "TreeCanonicalizer", "source_sha256",
    "tree_payload_sha256", "strip_checksums_section", "canonical_payload_bytes",
    "default_tree_canonicalizer",
]

PathLike = Union[str, Path]

#: Names the CHECKSUMS service section may appear under: the lowercase key
#: of :class:`tree_engine.storage.schema.TreeFile` and the upper-case
#: spelling of {p085}. Both are stripped, so either convention hashes alike.
CHECKSUMS_SECTION_KEYS = ("checksums", "CHECKSUMS")

#: Maps raw tree-file bytes to the canonical payload bytes that
#: :func:`tree_payload_sha256` consumes. Injectable so the codec layer can
#: supply its own version-pinned canonicalization ({p100}).
TreeCanonicalizer = Callable[[bytes], bytes]

# ---- Pure dual-SHA helpers ------------------------------------------------


def source_sha256(source_bytes: bytes) -> str:
    """SHA-256 hex digest of the exact source bytes, unnormalized ({p086}).

    Hashed verbatim, so the digest changes for a single flipped byte even
    when the file's size and mtime are unchanged.
    """
    return hashlib.sha256(source_bytes).hexdigest()


def tree_payload_sha256(canonical_payload: bytes) -> str:
    """SHA-256 hex digest of the canonical tree payload ({p086}).

    ``canonical_payload`` is the codec layer's deterministic serialization
    with CHECKSUMS already excluded; see :func:`canonical_payload_bytes`.
    """
    return hashlib.sha256(canonical_payload).hexdigest()


def strip_checksums_section(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy a decoded tree-file mapping without CHECKSUMS ({p086}); input unmutated."""
    if not isinstance(document, Mapping):
        raise TypeError(f"strip_checksums_section expects a mapping, got {type(document).__name__}")
    return {key: value for key, value in document.items() if key not in CHECKSUMS_SECTION_KEYS}


def canonical_payload_bytes(document: Mapping[str, Any]) -> bytes:
    """Canonicalize a decoded tree-file mapping to deterministic bytes.

    The default when the codec injects no version-pinned form ({p100}):
    CHECKSUMS dropped, keys sorted at every depth, minimal separators,
    UTF-8 -- so key order and file whitespace never move the digest.
    """
    stripped = strip_checksums_section(document)
    try:
        text = json.dumps(stripped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise TreePayloadInvalid(
            f"tree payload is not canonically serializable: {exc}", reason="not_serializable") from exc
    return text.encode("utf-8")


def default_tree_canonicalizer(raw_tree_file_bytes: bytes) -> bytes:
    """Map raw tree-file bytes to canonical payload bytes without CHECKSUMS.

    Safe and declarative per {p100}: a plain JSON decode, a section drop, a
    deterministic re-encode -- no ``eval``, ``exec``, ``pickle``, dynamic
    import. Raises ``TreePayloadInvalid`` on undecodable bytes.
    """
    try:
        document = json.loads(raw_tree_file_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TreePayloadInvalid(
            f"tree file is not decodable as a tree-file mapping: {exc}", reason="undecodable") from exc
    if not isinstance(document, Mapping):
        raise TreePayloadInvalid(
            f"tree file must decode to a mapping, got {type(document).__name__}", reason="not_a_mapping")
    return canonical_payload_bytes(document)

# ---- Evidence and verdict -------------------------------------------------


class ConflictResolutionPolicy(Enum):
    """Named policies under which a detected conflict may be overwritten.
    ``REFUSE`` is the default everywhere here; any other member must be
    named explicitly at the call site, so no boolean flag can relax the
    guard by accident ({p089})."""

    REFUSE = "refuse"
    OVERWRITE_SOURCE = "overwrite_source"
    OVERWRITE_TREE = "overwrite_tree"
    OVERWRITE_BOTH = "overwrite_both"

    def allows_source_overwrite(self) -> bool:
        """True only for the members that name a source overwrite."""
        return self in (ConflictResolutionPolicy.OVERWRITE_SOURCE, ConflictResolutionPolicy.OVERWRITE_BOTH)

    def allows_tree_overwrite(self) -> bool:
        """True only for the members that name a tree-file overwrite."""
        return self in (ConflictResolutionPolicy.OVERWRITE_TREE, ConflictResolutionPolicy.OVERWRITE_BOTH)


@dataclass(frozen=True)
class FileEvidence:
    """One file's on-disk facts at a single instant. ``sha256`` is the only
    field a verdict is derived from; ``size`` and ``mtime_ns`` are
    diagnostics, never a decision input ({p093}). ``sha256`` is None exactly
    when the file is missing or unreadable, and ``unreadable_reason`` says
    which."""

    path: Path
    exists: bool
    sha256: Optional[str] = None
    size: Optional[int] = None
    mtime_ns: Optional[int] = None
    unreadable_reason: Optional[str] = None


@dataclass(frozen=True)
class ConflictReport:
    """The outcome of one pre-write verification ({p089})."""

    source: FileEvidence
    tree: FileEvidence
    base_source_sha256: str
    base_tree_payload_sha256: str
    source_changed: bool
    tree_changed: bool

    @property
    def has_conflict(self) -> bool:
        """True when either file no longer matches its base digest."""
        return self.source_changed or self.tree_changed

    @property
    def error_code(self) -> Optional[ErrorCode]:
        """The code a refusing write signals; the source is reported first."""
        if self.source_changed:
            return ErrorCode.CONCURRENT_SOURCE_MODIFICATION
        if self.tree_changed:
            return ErrorCode.CONCURRENT_TREE_MODIFICATION
        return None

# ---- Session guard --------------------------------------------------------


class EditSession:
    """Session-scoped external-modification guard for one source/tree pair.

    Holds the base digests recorded when the external edit session opened
    and re-verifies them against real disk state before every write. That
    state lives here and never on the tree object ({p025}). Safe to share
    across threads: the mutable base digests are guarded by a private lock
    held only for the instant needed to read or advance them.
    """

    def __init__(
        self,
        source_path: PathLike,
        tree_path: PathLike,
        *,
        base_source_sha256: Optional[str] = None,
        base_tree_payload_sha256: Optional[str] = None,
        tree_canonicalizer: TreeCanonicalizer = default_tree_canonicalizer,
    ) -> None:
        """Open a session over ``source_path`` and ``tree_path``. Base
        digests default to the files' real digests now; a caller that
        already computed them while validating the pair may pass them
        instead of paying for a second read. A digest that cannot be
        established (absent or undecodable file) raises ``StorageIOError``."""
        self._source_path = Path(source_path)
        self._tree_path = Path(tree_path)
        self._canonicalize = tree_canonicalizer
        self._lock = threading.Lock()
        if base_source_sha256 is None:
            base_source_sha256 = self._require_digest(self._source_evidence())
        if base_tree_payload_sha256 is None:
            base_tree_payload_sha256 = self._require_digest(self._tree_evidence())
        self._base_source_sha256 = base_source_sha256
        self._base_tree_payload_sha256 = base_tree_payload_sha256

    @property
    def source_path(self) -> Path:
        """The source file this session guards."""
        return self._source_path

    @property
    def tree_path(self) -> Path:
        """The serialized tree file paired with that source."""
        return self._tree_path

    @property
    def base_source_sha256(self) -> str:
        """Digest of the source bytes this session was opened over."""
        with self._lock:
            return self._base_source_sha256

    @property
    def base_tree_payload_sha256(self) -> str:
        """Digest of the tree payload this session was opened over."""
        with self._lock:
            return self._base_tree_payload_sha256

    # -- disk evidence ------------------------------------------------------

    def _read_bytes(self, path: Path) -> Optional[bytes]:
        """Return the file's bytes, or None if it no longer exists. Only
        absence is reported as None, so a deletion is classified as an
        external modification; every other OS failure is a genuine I/O
        fault and raises ``StorageIOError``."""
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StorageIOError(f"cannot read {path}: {exc}", path=str(path), phase="verify_read") from exc

    def _evidence(self, path: Path, digest_of: Callable[[bytes], str]) -> FileEvidence:
        """On-disk facts for one file; the digest is None when it is missing
        or no longer readable as a payload. ``size``/``mtime_ns`` are read
        here as diagnostics only, never as a decision input ({p093})."""
        data = self._read_bytes(path)
        try:
            info = os.stat(path)
            size: Optional[int] = info.st_size
            mtime_ns: Optional[int] = info.st_mtime_ns
        except OSError:
            size, mtime_ns = None, None
        if data is None:
            return FileEvidence(path, False, None, size, mtime_ns, "missing")
        try:
            return FileEvidence(path, True, digest_of(data), size, mtime_ns)
        except TreePayloadInvalid as exc:
            return FileEvidence(path, True, None, size, mtime_ns, str(exc))

    def _source_evidence(self) -> FileEvidence:
        """Current on-disk facts about the source file."""
        return self._evidence(self._source_path, source_sha256)

    def _tree_evidence(self) -> FileEvidence:
        """Current on-disk facts about the tree file. A file that no longer
        canonicalizes yields no digest rather than a payload fault, so the
        caller sees CONCURRENT_TREE_MODIFICATION: external corruption is an
        external modification."""
        return self._evidence(self._tree_path, lambda raw: tree_payload_sha256(self._canonicalize(raw)))

    def _require_digest(self, evidence: FileEvidence) -> str:
        """Return the evidence digest, refusing to open a session without one."""
        if evidence.sha256 is None:
            raise StorageIOError(
                f"cannot open a session over {evidence.path}: {evidence.unreadable_reason}",
                path=str(evidence.path), phase="open_baseline")
        return evidence.sha256

    # -- verification -------------------------------------------------------

    def inspect(self) -> ConflictReport:
        """Recompute both digests from disk and report, without raising. A
        file that vanished or became undecodable has no current digest and
        counts as changed: the bytes this session was opened over are no
        longer the bytes on disk."""
        source = self._source_evidence()
        tree = self._tree_evidence()
        with self._lock:
            base_source = self._base_source_sha256
            base_tree = self._base_tree_payload_sha256
        return ConflictReport(
            source=source, tree=tree,
            base_source_sha256=base_source, base_tree_payload_sha256=base_tree,
            source_changed=source.sha256 != base_source,
            tree_changed=tree.sha256 != base_tree)

    def check_before_write(
        self, policy: ConflictResolutionPolicy = ConflictResolutionPolicy.REFUSE
    ) -> ConflictReport:
        """Verify the pair before a write and refuse on a conflict ({p089}).
        Returns the report when both files still match their base digests,
        or when ``policy`` names the overwrite covering each detected
        conflict. Otherwise raises ``ConcurrentSourceModification`` for a
        changed source and ``ConcurrentTreeModification`` for a changed tree
        file; the source is checked first."""
        if not isinstance(policy, ConflictResolutionPolicy):
            raise TypeError(
                f"policy must be a named ConflictResolutionPolicy member, got {type(policy).__name__}")
        report = self.inspect()
        if report.source_changed and not policy.allows_source_overwrite():
            raise ConcurrentSourceModification(
                f"source file {self._source_path} changed outside this edit session",
                path=str(self._source_path),
                base_source_sha256=report.base_source_sha256,
                current_source_sha256=report.source.sha256,
                exists=report.source.exists, reason=report.source.unreadable_reason)
        if report.tree_changed and not policy.allows_tree_overwrite():
            raise ConcurrentTreeModification(
                f"tree file {self._tree_path} changed outside this edit session",
                path=str(self._tree_path),
                base_tree_payload_sha256=report.base_tree_payload_sha256,
                current_tree_payload_sha256=report.tree.sha256,
                exists=report.tree.exists, reason=report.tree.unreadable_reason)
        return report

    def accept_publication(
        self, expected_source_sha256: str, expected_tree_payload_sha256: str
    ) -> ConflictReport:
        """Advance the base digests after a publish, once verified ({p091}).
        Re-reads both published files, recomputes both digests, and adopts
        them as the new baseline only when they equal what the publication
        claims to have written. A mismatch leaves the baseline untouched and
        raises ``ChecksumMismatch`` -- the caller's signal to run storage
        recovery rather than to mark the session clean."""
        source = self._source_evidence()
        tree = self._tree_evidence()
        if source.sha256 != expected_source_sha256:
            raise ChecksumMismatch(
                f"published source {self._source_path} does not match its expected digest",
                path=str(self._source_path), expected_source_sha256=expected_source_sha256,
                actual_source_sha256=source.sha256)
        if tree.sha256 != expected_tree_payload_sha256:
            raise ChecksumMismatch(
                f"published tree file {self._tree_path} does not match its expected digest",
                path=str(self._tree_path),
                expected_tree_payload_sha256=expected_tree_payload_sha256,
                actual_tree_payload_sha256=tree.sha256)
        with self._lock:
            self._base_source_sha256 = expected_source_sha256
            self._base_tree_payload_sha256 = expected_tree_payload_sha256
        return ConflictReport(
            source=source, tree=tree,
            base_source_sha256=expected_source_sha256,
            base_tree_payload_sha256=expected_tree_payload_sha256,
            source_changed=False, tree_changed=False)
