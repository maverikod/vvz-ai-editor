# marked_tree_unification — a8 Baseline File Contents

Generated: 2026-05-30. On-disk reads + simulated prior-AS edits per execution order.

## Requested AS Summary

| AS_id | target | baseline_line_count | post_impl_estimate | STOP |
|-------|--------|--------------------:|-------------------:|:----:|
| G-002/T-002/A-001 | checksum.py | 233 | 311 | N |
| G-002/T-004/A-001 | checksum.py | 311 | 312 | N |
| G-000/T-003/A-007 | checksum.py | 309 | 309 | N |
| G-005/T-001/A-001 | grep_block_resolver.py | 289 | 290 | N |
| G-000/T-003/A-003 | grep_block_resolver.py | 289 | 289 | N |
| G-000/T-003/A-010 | tree_builder.py | 704 | 704 | Y* |
| G-000/T-003/A-012 | tree_builder.py | 704 | ~310-377 | N |
| G-001/T-003/A-003 | handler_registry.py | 53 | 115 | N |

\* A-010 is docstring-only scoped edit on 704L file — a3 scoped exception, not a TS split STOP.

### A-007 line-count confirmation

User estimate ~318L; **correct chained baseline is 309L** (not 318). A-007 YAML embed (296L content block) is stale — predates G-002/T-002/A-001 and G-002/T-004/A-001.

---


## G-002/T-002/A-001

**Target:** `code_analysis/core/tree_lifecycle/checksum.py`  
**Baseline line count:** 233  


```python
"""
Centralized tree-lifecycle: checksum + validate + recreate.

This module owns ONE responsibility: "is there a valid tree (sidecar) for this
content; if not, build it". Every consumer that needs a structurally valid tree
(preview, grep, watcher, indexer, edit sessions, builders) routes through here
so the rule lives in a single place.

Design:
- The CORE works on CONTENT (strings), not file paths. Builders and edit
  sessions that already hold the source text in memory call the core directly,
  avoiding a redundant file read.
- A thin FILE wrapper sits on top: it reads the source once, computes the
  checksum, reads the sidecar digest, and delegates to the core.

Representation building (turning a valid tree into a preview/structure) is NOT
this module's job — that stays in ``tree_representation``. This module only
guarantees the tree is valid and rebuilds it when stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from code_analysis.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
    classify_tree_format,
    sidecar_path_for,
)


def compute_content_checksum(content: str) -> str:
    """Return the SHA-256 hex digest of *content*.

    This is the content-based counterpart of hashing a file: callers that hold
    the source text in memory hash it directly, without touching disk.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_tree_valid(content_checksum: str, sidecar_digest: str | None) -> bool:
    """Return True when a sidecar digest exists and matches the content checksum."""
    return sidecar_digest is not None and sidecar_digest == content_checksum


def recreate_tree_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild the sidecar tree for *content* using the per-format tree builders.

    Takes the already-in-memory ``content`` instead of re-reading the file, so a
    caller that just hashed the content does not pay a second read. Writes the
    sidecar atomically and returns a validated reference.
    """
    # Local imports break a module-load cycle with tree_representation and keep
    # the per-format builder dependencies lazy (heavy modules).
    if kind == TreeFormatKind.python_cst:
        from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
        from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic
        from code_analysis.core.search_session.tree_representation import (
            _read_cst_digest_and_root,
        )

        create_tree_from_code(str(source_abs), content, persist_sidecar=True)
        if not sidecar_path.is_file():
            write_sidecar_atomic(source_abs, {"source_sha256": content_checksum})
        _digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )

    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        from code_analysis.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )
        from code_analysis.core.search_session.tree_representation import (
            _read_tree_temp_root_stable_id,
        )

        if kind == TreeFormatKind.json:
            from code_analysis.core.json_tree.tree_builder import build_tree_from_data

            data = json.loads(content)
            tree = build_tree_from_data(data, source_path=str(source_abs))
        else:
            import yaml as _yaml

            from code_analysis.core.yaml_tree.tree_builder import (
                build_yaml_tree_from_data,
            )

            data = _yaml.safe_load(content)
            tree = build_yaml_tree_from_data(data, source_path=str(source_abs))

        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )

    # markdown or plain text — adjacent .tree_sidecar
    from code_analysis.core.structure_extraction.extractor import extract_structure
    from code_analysis.core.search_session.tree_representation import (
        _read_adjacent_root_stable_id,
    )

    extract_structure(str(source_abs), ensure_persisted_tree=True)
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    sidecar_digest: str | None,
    root_stable_id: str | None,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """Decide reuse vs recreate for already-in-memory *content*.

    The caller supplies the current sidecar digest (and root stable id) it has
    already read. When the digest matches the content checksum and ``force`` is
    false, the existing sidecar is reused; otherwise the tree is rebuilt.
    """
    content_checksum = compute_content_checksum(content)
    if not force and is_tree_valid(content_checksum, sidecar_digest):
        return (
            TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            ),
            TreeValidityState.reused,
        )
    ref = recreate_tree_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        content_checksum=content_checksum,
    )
    return ref, TreeValidityState.recreated


def validate_or_recreate_tree_file(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """File wrapper over the content core.

    Reads the source once, computes its checksum, reads the current sidecar
    digest, then delegates to ``validate_or_recreate_from_content``. This is the
    entry point for path-based consumers (preview, grep, watcher).

    Raises FileNotFoundError when the source file is absent.
    """
    from code_analysis.core.search_session.tree_representation import (
        _read_sidecar_state,
    )

    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, root)
    sidecar_digest, root_stable_id = _read_sidecar_state(
        kind=kind, source_abs=source_abs, sidecar_path=sidecar_path
    )
    return validate_or_recreate_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        sidecar_digest=sidecar_digest,
        root_stable_id=root_stable_id,
        force=force,
    )


__all__ = [
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
```


## G-002/T-004/A-001

**Target:** `code_analysis/core/tree_lifecycle/checksum.py`  
**Baseline line count:** 311  
**Chain:** post G-002/T-002/A-001 (ChecksumSyncPolicy added).

```python
"""
Centralized tree-lifecycle: checksum + validate + recreate.

This module owns ONE responsibility: "is there a valid tree (sidecar) for this
content; if not, build it". Every consumer that needs a structurally valid tree
(preview, grep, watcher, indexer, edit sessions, builders) routes through here
so the rule lives in a single place.

Design:
- The CORE works on CONTENT (strings), not file paths. Builders and edit
  sessions that already hold the source text in memory call the core directly,
  avoiding a redundant file read.
- A thin FILE wrapper sits on top: it reads the source once, computes the
  checksum, reads the sidecar digest, and delegates to the core.

Representation building (turning a valid tree into a preview/structure) is NOT
this module's job — that stays in ``tree_representation``. This module only
guarantees the tree is valid and rebuilds it when stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from code_analysis.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
    classify_tree_format,
    sidecar_path_for,
)

from code_analysis.commands.universal_file_edit.sha_sync_policy import (
    ShaSyncBranch,
    ShaSyncDecision,
    resolve_sha_sync_policy,
)


def compute_content_checksum(content: str) -> str:
    """Return the SHA-256 hex digest of *content*.

    This is the content-based counterpart of hashing a file: callers that hold
    the source text in memory hash it directly, without touching disk.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_tree_valid(content_checksum: str, sidecar_digest: str | None) -> bool:
    """Return True when a sidecar digest exists and matches the content checksum."""
    return sidecar_digest is not None and sidecar_digest == content_checksum

class ChecksumSyncPolicy:
    """ChecksumSyncPolicy (C-006): four-branch tree-vs-source truth decision.

    This is the single mechanism that decides whether a TreeFile (C-003) is
    current with respect to its SourceFile (C-004), based solely on SHA-256
    checksums. Checksum computation and verification are the only synchronization
    trigger; mtime, size, and other file metadata are not used.

    Four-branch decision table (applies uniformly to all formats):

    Branch 1 -- NO_SIDECAR (ShaSyncBranch.NO_SIDECAR):
        Precondition: no co-located TreeFile exists.
        Action: build a new tree from the SourceFile content.

    Branch 2 -- SHA_MATCH (ShaSyncBranch.SHA_MATCH):
        Precondition: TreeFile present; stored checksum == current source
        checksum.
        Action: tree is current; no rebuild needed.

    Branch 3 -- SHA_MISMATCH_NO_SESSION (ShaSyncBranch.SHA_MISMATCH_NO_SESSION):
        Precondition: TreeFile present; checksums differ; no active edit
        session holds the file.
        Action: tree is stale; rebuild from SourceFile content.

    Branch 4 -- SHA_MISMATCH_ACTIVE_SESSION
    (ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION):
        Precondition: TreeFile present; checksums differ; an active edit
        session holds the file.
        Action: tree is truth, source copy inside session is stale;
        do NOT rebuild -- the session tree takes precedence.

    Session-truth invariant (C-006, HRS {a005}):
        Inside an active edit session the tree is the source of truth.
        Outside any session the SourceFile (C-004) is the source of truth.
    """

    #: Re-export the branch enum so callers need only import this class.
    Branch = ShaSyncBranch

    @staticmethod
    def decide(
        *,
        tree_file_present: bool,
        stored_checksum: str | None,
        current_checksum: str,
        active_session: bool,
    ) -> ShaSyncDecision:
        """Run the four-branch decision for one file.

        Args:
            tree_file_present: True when a co-located TreeFile exists on disk.
            stored_checksum: SHA-256 hex digest stored in the TreeFile, or None
                when the TreeFile is absent or its digest is unreadable.
            current_checksum: SHA-256 hex digest of the current SourceFile
                content, produced by :func:`compute_content_checksum`.
            active_session: True when an active edit session currently holds
                the file; the session tree is the source of truth in that case.

        Returns:
            A :class:`ShaSyncDecision` whose ``branch`` attribute identifies
            which of the four branches applies.
        """
        return resolve_sha_sync_policy(
            sidecar_exists=tree_file_present,
            sidecar_source_sha256=stored_checksum,
            current_source_sha256=current_checksum,
            active_session_holds_file=active_session,
        )


def recreate_tree_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild the sidecar tree for *content* using the per-format tree builders.

    Takes the already-in-memory ``content`` instead of re-reading the file, so a
    caller that just hashed the content does not pay a second read. Writes the
    sidecar atomically and returns a validated reference.
    """
    # Local imports break a module-load cycle with tree_representation and keep
    # the per-format builder dependencies lazy (heavy modules).
    if kind == TreeFormatKind.python_cst:
        from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
        from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic
        from code_analysis.core.search_session.tree_representation import (
            _read_cst_digest_and_root,
        )

        create_tree_from_code(str(source_abs), content, persist_sidecar=True)
        if not sidecar_path.is_file():
            write_sidecar_atomic(source_abs, {"source_sha256": content_checksum})
        _digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )

    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        from code_analysis.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )
        from code_analysis.core.search_session.tree_representation import (
            _read_tree_temp_root_stable_id,
        )

        if kind == TreeFormatKind.json:
            from code_analysis.core.json_tree.tree_builder import build_tree_from_data

            data = json.loads(content)
            tree = build_tree_from_data(data, source_path=str(source_abs))
        else:
            import yaml as _yaml

            from code_analysis.core.yaml_tree.tree_builder import (
                build_yaml_tree_from_data,
            )

            data = _yaml.safe_load(content)
            tree = build_yaml_tree_from_data(data, source_path=str(source_abs))

        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )

    # markdown or plain text — adjacent .tree_sidecar
    from code_analysis.core.structure_extraction.extractor import extract_structure
    from code_analysis.core.search_session.tree_representation import (
        _read_adjacent_root_stable_id,
    )

    extract_structure(str(source_abs), ensure_persisted_tree=True)
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    sidecar_digest: str | None,
    root_stable_id: str | None,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """Decide reuse vs recreate for already-in-memory *content*.

    The caller supplies the current sidecar digest (and root stable id) it has
    already read. When the digest matches the content checksum and ``force`` is
    false, the existing sidecar is reused; otherwise the tree is rebuilt.
    """
    content_checksum = compute_content_checksum(content)
    if not force and is_tree_valid(content_checksum, sidecar_digest):
        return (
            TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            ),
            TreeValidityState.reused,
        )
    ref = recreate_tree_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        content_checksum=content_checksum,
    )
    return ref, TreeValidityState.recreated


def validate_or_recreate_tree_file(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """File wrapper over the content core.

    Reads the source once, computes its checksum, reads the current sidecar
    digest, then delegates to ``validate_or_recreate_from_content``. This is the
    entry point for path-based consumers (preview, grep, watcher).

    Raises FileNotFoundError when the source file is absent.
    """
    from code_analysis.core.search_session.tree_representation import (
        _read_sidecar_state,
    )

    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, root)
    sidecar_digest, root_stable_id = _read_sidecar_state(
        kind=kind, source_abs=source_abs, sidecar_path=sidecar_path
    )
    return validate_or_recreate_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        sidecar_digest=sidecar_digest,
        root_stable_id=root_stable_id,
        force=force,
    )


__all__ = [
    "ChecksumSyncPolicy",
    "ShaSyncBranch",
    "ShaSyncDecision",
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
```


## G-000/T-003/A-007

**Target:** `code_analysis/core/tree_lifecycle/checksum.py`  
**Baseline line count:** 309  
**Chain:** post G-002/T-004/A-001 (TreeBuilder.build wired). A-007 YAML embed is **stale** (233L, no ChecksumSyncPolicy/TreeBuilder). Correct baseline is this 309L file.

```python
"""
Centralized tree-lifecycle: checksum + validate + recreate.

This module owns ONE responsibility: "is there a valid tree (sidecar) for this
content; if not, build it". Every consumer that needs a structurally valid tree
(preview, grep, watcher, indexer, edit sessions, builders) routes through here
so the rule lives in a single place.

Design:
- The CORE works on CONTENT (strings), not file paths. Builders and edit
  sessions that already hold the source text in memory call the core directly,
  avoiding a redundant file read.
- A thin FILE wrapper sits on top: it reads the source once, computes the
  checksum, reads the sidecar digest, and delegates to the core.

Representation building (turning a valid tree into a preview/structure) is NOT
this module's job — that stays in ``tree_representation``. This module only
guarantees the tree is valid and rebuilds it when stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from code_analysis.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
    classify_tree_format,
    sidecar_path_for,
)

from code_analysis.commands.universal_file_edit.sha_sync_policy import (
    ShaSyncBranch,
    ShaSyncDecision,
    resolve_sha_sync_policy,
)
from code_analysis.core.tree_lifecycle.builder import TreeBuilder


def compute_content_checksum(content: str) -> str:
    """Return the SHA-256 hex digest of *content*.

    This is the content-based counterpart of hashing a file: callers that hold
    the source text in memory hash it directly, without touching disk.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_tree_valid(content_checksum: str, sidecar_digest: str | None) -> bool:
    """Return True when a sidecar digest exists and matches the content checksum."""
    return sidecar_digest is not None and sidecar_digest == content_checksum

class ChecksumSyncPolicy:
    """ChecksumSyncPolicy (C-006): four-branch tree-vs-source truth decision.

    This is the single mechanism that decides whether a TreeFile (C-003) is
    current with respect to its SourceFile (C-004), based solely on SHA-256
    checksums. Checksum computation and verification are the only synchronization
    trigger; mtime, size, and other file metadata are not used.

    Four-branch decision table (applies uniformly to all formats):

    Branch 1 -- NO_SIDECAR (ShaSyncBranch.NO_SIDECAR):
        Precondition: no co-located TreeFile exists.
        Action: build a new tree from the SourceFile content.

    Branch 2 -- SHA_MATCH (ShaSyncBranch.SHA_MATCH):
        Precondition: TreeFile present; stored checksum == current source
        checksum.
        Action: tree is current; no rebuild needed.

    Branch 3 -- SHA_MISMATCH_NO_SESSION (ShaSyncBranch.SHA_MISMATCH_NO_SESSION):
        Precondition: TreeFile present; checksums differ; no active edit
        session holds the file.
        Action: tree is stale; rebuild from SourceFile content.

    Branch 4 -- SHA_MISMATCH_ACTIVE_SESSION
    (ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION):
        Precondition: TreeFile present; checksums differ; an active edit
        session holds the file.
        Action: tree is truth, source copy inside session is stale;
        do NOT rebuild -- the session tree takes precedence.

    Session-truth invariant (C-006, HRS {a005}):
        Inside an active edit session the tree is the source of truth.
        Outside any session the SourceFile (C-004) is the source of truth.
    """

    #: Re-export the branch enum so callers need only import this class.
    Branch = ShaSyncBranch

    @staticmethod
    def decide(
        *,
        tree_file_present: bool,
        stored_checksum: str | None,
        current_checksum: str,
        active_session: bool,
    ) -> ShaSyncDecision:
        """Run the four-branch decision for one file.

        Args:
            tree_file_present: True when a co-located TreeFile exists on disk.
            stored_checksum: SHA-256 hex digest stored in the TreeFile, or None
                when the TreeFile is absent or its digest is unreadable.
            current_checksum: SHA-256 hex digest of the current SourceFile
                content, produced by :func:`compute_content_checksum`.
            active_session: True when an active edit session currently holds
                the file; the session tree is the source of truth in that case.

        Returns:
            A :class:`ShaSyncDecision` whose ``branch`` attribute identifies
            which of the four branches applies.
        """
        return resolve_sha_sync_policy(
            sidecar_exists=tree_file_present,
            sidecar_source_sha256=stored_checksum,
            current_source_sha256=current_checksum,
            active_session_holds_file=active_session,
        )


def recreate_tree_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild the sidecar tree for *content* using the per-format tree builders.

    Takes the already-in-memory ``content`` instead of re-reading the file, so a
    caller that just hashed the content does not pay a second read. Writes the
    sidecar atomically and returns a validated reference.
    """
    # Local imports break a module-load cycle with tree_representation and keep
    # the per-format builder dependencies lazy (heavy modules).
    if kind == TreeFormatKind.python_cst:
        from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
        from code_analysis.core.search_session.tree_representation import (
            _read_cst_digest_and_root,
        )

        create_tree_from_code(str(source_abs), content, persist_sidecar=True)
        _digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )

    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        from code_analysis.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )
        from code_analysis.core.search_session.tree_representation import (
            _read_tree_temp_root_stable_id,
        )

        if kind == TreeFormatKind.json:
            from code_analysis.core.json_tree.tree_builder import build_tree_from_data

            data = json.loads(content)
            tree = build_tree_from_data(data, source_path=str(source_abs))
        else:
            import yaml as _yaml

            from code_analysis.core.yaml_tree.tree_builder import (
                build_yaml_tree_from_data,
            )

            data = _yaml.safe_load(content)
            tree = build_yaml_tree_from_data(data, source_path=str(source_abs))

        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )

    # markdown or plain text — adjacent .tree_sidecar
    from code_analysis.core.structure_extraction.extractor import extract_structure
    from code_analysis.core.search_session.tree_representation import (
        _read_adjacent_root_stable_id,
    )

    extract_structure(str(source_abs), ensure_persisted_tree=True)
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    sidecar_digest: str | None,
    root_stable_id: str | None,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """Decide reuse vs recreate for already-in-memory *content*.

    The caller supplies the current sidecar digest (and root stable id) it has
    already read. When the digest matches the content checksum and ``force`` is
    false, the existing sidecar is reused; otherwise the tree is rebuilt.
    """
    content_checksum = compute_content_checksum(content)
    if not force and is_tree_valid(content_checksum, sidecar_digest):
        return (
            TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            ),
            TreeValidityState.reused,
        )
    ref = TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=file_path,
        content_checksum=content_checksum,
    )
    if ref.sidecar_path != sidecar_path:
        sidecar_path = ref.sidecar_path
    return ref, TreeValidityState.recreated


def validate_or_recreate_tree_file(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """File wrapper over the content core.

    Reads the source once, computes its checksum, reads the current sidecar
    digest, then delegates to ``validate_or_recreate_from_content``. This is the
    entry point for path-based consumers (preview, grep, watcher).

    Raises FileNotFoundError when the source file is absent.
    """
    from code_analysis.core.search_session.tree_representation import (
        _read_sidecar_state,
    )

    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, root)
    sidecar_digest, root_stable_id = _read_sidecar_state(
        kind=kind, source_abs=source_abs, sidecar_path=sidecar_path
    )
    return validate_or_recreate_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        sidecar_digest=sidecar_digest,
        root_stable_id=root_stable_id,
        force=force,
    )


__all__ = [
    "ChecksumSyncPolicy",
    "ShaSyncBranch",
    "ShaSyncDecision",
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
```


## G-005/T-001/A-001

**Target:** `code_analysis/commands/grep_block_resolver.py`  
**Baseline line count:** 289  


```python
"""
Resolve grep match lines to preview/edit block identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from code_analysis.core.structure_extraction.models import StructureDocument

from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    _line_for_json_pointer,
)
from code_analysis.commands.universal_file_preview.handlers.markdown_handler import (
    _iter_md_block_tokens,
    _md_block_node_ref,
)
from code_analysis.commands.universal_file_preview.handlers.yaml_handler import (
    _line_for_yaml_pointer,
)
from code_analysis.core.cst_tree.models import TreeNodeMetadata
from code_analysis.core.cst_tree.tree_sidecar import (
    metadata_map_from_payload,
    read_sidecar_payload,
    sidecar_path_for_py,
)
from code_analysis.core.json_tree.tree_builder import build_tree_from_data
from code_analysis.core.yaml_tree.tree_builder import build_yaml_tree_from_data

_PY_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})
_JSON_SUFFIX = ".json"
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
_MD_SUFFIX = ".md"

_TRIVIAL_NODE_TYPES = frozenset(
    {
        "SimpleWhitespace",
        "TrailingWhitespace",
        "Newline",
        "EmptyLine",
        "Comment",
        "Whitespace",
    }
)

_PREFERRED_SIDECAR_KINDS = frozenset(
    {"method", "function", "class", "stmt", "smallstmt", "module"}
)

_CacheKey = tuple[str, float]


class GrepBlockResolver:
    """Per-file cached lookup from 1-based line number to block id/type.

    Prefer :func:`code_analysis.core.structure_extraction.extract_structure` for
    new code; this class remains for legacy callers.
    """

    def __init__(self) -> None:
        self._indexes: dict[_CacheKey, _LineBlockIndex | None] = {}
        self._documents: dict[_CacheKey, "StructureDocument | None"] = {}

    def resolve(
        self, abs_path: Path, line_number: int
    ) -> tuple[str | None, str | None]:
        from code_analysis.core.structure_extraction.extractor import (
            extract_structure,
            find_smallest_block_containing_line,
        )

        cache_key = _cache_key(abs_path)
        if cache_key not in self._documents:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._documents[cache_key] = None
            else:
                self._documents[cache_key] = extract_structure(
                    file_path=str(abs_path),
                    content=content,
                    source="disk",
                )
        document = self._documents.get(cache_key)
        if document is None:
            return None, None
        block = find_smallest_block_containing_line(document, line_number)
        if block is None:
            return None, None
        return block.block_id, block.node_type

    def cleanup(self) -> None:
        self._indexes.clear()
        self._documents.clear()


class _LineBlockIndex:
    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        raise NotImplementedError


class _SidecarPythonLineBlockIndex(_LineBlockIndex):
    """Lookup via ``.cst/{stem}.tree`` metadata_map (no in-memory CST session)."""

    def __init__(self, metadata_map: dict[str, TreeNodeMetadata]) -> None:
        self._metadata = list(metadata_map.values())
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        if line_number in self._cache:
            return self._cache[line_number]
        candidates = [
            meta
            for meta in self._metadata
            if meta.start_line <= line_number <= meta.end_line
            and meta.type not in _TRIVIAL_NODE_TYPES
            and meta.kind in _PREFERRED_SIDECAR_KINDS
        ]
        if not candidates:
            result = (None, None)
        else:
            best = min(
                candidates,
                key=lambda meta: (
                    meta.end_line - meta.start_line,
                    meta.start_line,
                ),
            )
            result = (best.stable_id, best.type)
        self._cache[line_number] = result
        return result


class _StructuredLineBlockIndex(_LineBlockIndex):
    def __init__(self, line_map: dict[int, tuple[str, str]]) -> None:
        self._line_map = line_map

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        hit = self._line_map.get(line_number)
        if hit is None:
            return None, None
        return hit[0], hit[1]


class _MarkdownLineBlockIndex(_LineBlockIndex):
    def __init__(self, abs_path: Path, tokens: list[Any]) -> None:
        self._file_path = str(abs_path.resolve())
        self._tokens = tokens
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        if line_number in self._cache:
            return self._cache[line_number]
        zero_line = line_number - 1
        best = None
        best_span: int | None = None
        for token in self._tokens:
            if token.map is None:
                continue
            start, end = token.map
            if start <= zero_line < end:
                span = end - start
                if best is None or span <= best_span:
                    best = token
                    best_span = span
        if best is None:
            result = (None, None)
        else:
            result = (_md_block_node_ref(self._file_path, best), best.type)
        self._cache[line_number] = result
        return result


def _cache_key(abs_path: Path) -> _CacheKey:
    resolved = abs_path.resolve()
    try:
        mtime = resolved.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (str(resolved), mtime)


def _build_line_to_node_id_map(
    source: str,
    metadata_map: dict[str, Any],
    line_for_pointer,
    pointer_attr: str,
) -> dict[int, tuple[str, str]]:
    """
    Expand annotated start-line refs to every source line (nearest ancestor node).

    Same strategy as universal_file_preview annotated_full_text: map each node's
    start line via pointer heuristics, then assign each file line the deepest
    node whose start line is still on or above that line.
    """
    lines = source.splitlines()
    if not lines:
        return {}
    starts: list[tuple[int, str, str]] = []
    for meta in metadata_map.values():
        pointer = getattr(meta, pointer_attr, "")
        start = getattr(meta, "start_line", None)
        if start is None:
            start = line_for_pointer(lines, pointer)
        if start is None:
            continue
        starts.append((start, meta.node_id, meta.kind))
    starts.sort(key=lambda item: item[0])
    if not starts:
        return {}
    line_map: dict[int, tuple[str, str]] = {}
    for line_num in range(1, len(lines) + 1):
        best: tuple[str, str] | None = None
        best_start = -1
        for start, node_id, kind in starts:
            if start <= line_num and start >= best_start:
                best_start = start
                best = (node_id, kind)
        if best is not None:
            line_map[line_num] = best
    return line_map


def _load_python_sidecar_index(abs_path: Path) -> _SidecarPythonLineBlockIndex | None:
    sidecar_path = sidecar_path_for_py(abs_path)
    if not sidecar_path.is_file():
        return None
    try:
        py_mtime = abs_path.stat().st_mtime
        sidecar_mtime = sidecar_path.stat().st_mtime
    except OSError:
        return None
    if py_mtime > sidecar_mtime:
        return None
    payload = read_sidecar_payload(abs_path)
    if payload is None:
        return None
    meta_blob = payload.get("metadata_map")
    order_raw = payload.get("metadata_node_order")
    order = [str(x) for x in order_raw] if isinstance(order_raw, list) else None
    metadata_map = metadata_map_from_payload(meta_blob, order)
    if not metadata_map:
        return None
    return _SidecarPythonLineBlockIndex(metadata_map)


def _build_index(abs_path: Path) -> _LineBlockIndex | None:
    suffix = abs_path.suffix.lower()
    try:
        if suffix in _PY_SUFFIXES:
            return _load_python_sidecar_index(abs_path)
        source = abs_path.read_text(encoding="utf-8", errors="replace")
        if suffix == _JSON_SUFFIX:
            import json

            data = json.loads(source)
            tree = build_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_json_pointer,
                "json_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix in _YAML_SUFFIXES:
            import yaml

            data = yaml.safe_load(source)
            tree = build_yaml_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_yaml_pointer,
                "yaml_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix == _MD_SUFFIX:
            from markdown_it import MarkdownIt

            tokens = list(_iter_md_block_tokens(MarkdownIt().parse(source)))
            return _MarkdownLineBlockIndex(abs_path, tokens)
    except Exception:
        return None
    return None
```


## G-000/T-003/A-003

**Target:** `code_analysis/commands/grep_block_resolver.py`  
**Baseline line count:** 289  
**Chain:** post G-005/T-001/A-001 (TreeLifecycle routing).

```python
"""
Resolve grep match lines to preview/edit block identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from code_analysis.core.structure_extraction.models import StructureDocument

from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    _line_for_json_pointer,
)
from code_analysis.commands.universal_file_preview.handlers.markdown_handler import (
    _iter_md_block_tokens,
    _md_block_node_ref,
)
from code_analysis.commands.universal_file_preview.handlers.yaml_handler import (
    _line_for_yaml_pointer,
)
from code_analysis.core.cst_tree.models import TreeNodeMetadata
from code_analysis.core.cst_tree.tree_sidecar import (
    metadata_map_from_payload,
    read_sidecar_payload,
)
from code_analysis.core.json_tree.tree_builder import build_tree_from_data
from code_analysis.core.tree_lifecycle.checksum import validate_or_recreate_tree_file
from code_analysis.core.yaml_tree.tree_builder import build_yaml_tree_from_data

_PY_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})
_JSON_SUFFIX = ".json"
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
_MD_SUFFIX = ".md"

_TRIVIAL_NODE_TYPES = frozenset(
    {
        "SimpleWhitespace",
        "TrailingWhitespace",
        "Newline",
        "EmptyLine",
        "Comment",
        "Whitespace",
    }
)

_PREFERRED_SIDECAR_KINDS = frozenset(
    {"method", "function", "class", "stmt", "smallstmt", "module"}
)

_CacheKey = tuple[str, float]


class GrepBlockResolver:
    """Per-file cached lookup from 1-based line number to block id/type.

    Prefer :func:`code_analysis.core.structure_extraction.extract_structure` for
    new code; this class remains for legacy callers.
    """

    def __init__(self) -> None:
        self._indexes: dict[_CacheKey, _LineBlockIndex | None] = {}
        self._documents: dict[_CacheKey, "StructureDocument | None"] = {}

    def resolve(
        self, abs_path: Path, line_number: int
    ) -> tuple[str | None, str | None]:
        from code_analysis.core.structure_extraction.extractor import (
            extract_structure,
            find_smallest_block_containing_line,
        )

        cache_key = _cache_key(abs_path)
        if cache_key not in self._documents:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._documents[cache_key] = None
            else:
                self._documents[cache_key] = extract_structure(
                    file_path=str(abs_path),
                    content=content,
                    source="disk",
                )
        document = self._documents.get(cache_key)
        if document is None:
            return None, None
        block = find_smallest_block_containing_line(document, line_number)
        if block is None:
            return None, None
        return block.block_id, block.node_type

    def cleanup(self) -> None:
        self._indexes.clear()
        self._documents.clear()


class _LineBlockIndex:
    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        raise NotImplementedError


class _SidecarPythonLineBlockIndex(_LineBlockIndex):
    """Lookup via TreeLifecycle-validated sibling ``<source>.py.tree`` metadata_map (no in-memory CST session)."""

    def __init__(self, metadata_map: dict[str, TreeNodeMetadata]) -> None:
        self._metadata = list(metadata_map.values())
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        if line_number in self._cache:
            return self._cache[line_number]
        candidates = [
            meta
            for meta in self._metadata
            if meta.start_line <= line_number <= meta.end_line
            and meta.type not in _TRIVIAL_NODE_TYPES
            and meta.kind in _PREFERRED_SIDECAR_KINDS
        ]
        if not candidates:
            result = (None, None)
        else:
            best = min(
                candidates,
                key=lambda meta: (
                    meta.end_line - meta.start_line,
                    meta.start_line,
                ),
            )
            result = (best.stable_id, best.type)
        self._cache[line_number] = result
        return result


class _StructuredLineBlockIndex(_LineBlockIndex):
    def __init__(self, line_map: dict[int, tuple[str, str]]) -> None:
        self._line_map = line_map

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        hit = self._line_map.get(line_number)
        if hit is None:
            return None, None
        return hit[0], hit[1]


class _MarkdownLineBlockIndex(_LineBlockIndex):
    def __init__(self, abs_path: Path, tokens: list[Any]) -> None:
        self._file_path = str(abs_path.resolve())
        self._tokens = tokens
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        if line_number in self._cache:
            return self._cache[line_number]
        zero_line = line_number - 1
        best = None
        best_span: int | None = None
        for token in self._tokens:
            if token.map is None:
                continue
            start, end = token.map
            if start <= zero_line < end:
                span = end - start
                if best is None or span <= best_span:
                    best = token
                    best_span = span
        if best is None:
            result = (None, None)
        else:
            result = (_md_block_node_ref(self._file_path, best), best.type)
        self._cache[line_number] = result
        return result


def _cache_key(abs_path: Path) -> _CacheKey:
    resolved = abs_path.resolve()
    try:
        mtime = resolved.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (str(resolved), mtime)


def _build_line_to_node_id_map(
    source: str,
    metadata_map: dict[str, Any],
    line_for_pointer,
    pointer_attr: str,
) -> dict[int, tuple[str, str]]:
    """
    Expand annotated start-line refs to every source line (nearest ancestor node).

    Same strategy as universal_file_preview annotated_full_text: map each node's
    start line via pointer heuristics, then assign each file line the deepest
    node whose start line is still on or above that line.
    """
    lines = source.splitlines()
    if not lines:
        return {}
    starts: list[tuple[int, str, str]] = []
    for meta in metadata_map.values():
        pointer = getattr(meta, pointer_attr, "")
        start = getattr(meta, "start_line", None)
        if start is None:
            start = line_for_pointer(lines, pointer)
        if start is None:
            continue
        starts.append((start, meta.node_id, meta.kind))
    starts.sort(key=lambda item: item[0])
    if not starts:
        return {}
    line_map: dict[int, tuple[str, str]] = {}
    for line_num in range(1, len(lines) + 1):
        best: tuple[str, str] | None = None
        best_start = -1
        for start, node_id, kind in starts:
            if start <= line_num and start >= best_start:
                best_start = start
                best = (node_id, kind)
        if best is not None:
            line_map[line_num] = best
    return line_map


def _load_python_sidecar_index(abs_path: Path) -> _SidecarPythonLineBlockIndex | None:
    resolved = abs_path.resolve()
    try:
        tree_ref, _state = validate_or_recreate_tree_file(
            project_root=resolved.parent,
            file_path=resolved.name,
        )
    except (FileNotFoundError, ValueError, OSError, NotImplementedError):
        return None
    if not tree_ref.sidecar_path.is_file():
        return None
    payload = read_sidecar_payload(abs_path)
    if payload is None:
        return None
    meta_blob = payload.get("metadata_map")
    order_raw = payload.get("metadata_node_order")
    order = [str(x) for x in order_raw] if isinstance(order_raw, list) else None
    metadata_map = metadata_map_from_payload(meta_blob, order)
    if not metadata_map:
        return None
    return _SidecarPythonLineBlockIndex(metadata_map)


def _build_index(abs_path: Path) -> _LineBlockIndex | None:
    suffix = abs_path.suffix.lower()
    try:
        if suffix in _PY_SUFFIXES:
            return _load_python_sidecar_index(abs_path)
        source = abs_path.read_text(encoding="utf-8", errors="replace")
        if suffix == _JSON_SUFFIX:
            import json

            data = json.loads(source)
            tree = build_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_json_pointer,
                "json_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix in _YAML_SUFFIXES:
            import yaml

            data = yaml.safe_load(source)
            tree = build_yaml_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_yaml_pointer,
                "yaml_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix == _MD_SUFFIX:
            from markdown_it import MarkdownIt

            tokens = list(_iter_md_block_tokens(MarkdownIt().parse(source)))
            return _MarkdownLineBlockIndex(abs_path, tokens)
    except Exception:
        return None
    return None
```


## G-000/T-003/A-010

**Target:** `code_analysis/core/cst_tree/tree_builder.py`  
**Baseline line count:** 704  
**Note:** A-010 YAML lacks full embed; baseline is on-disk pre-step state.

```python
"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_key_to_id_from_metadata,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from .node_type_utils import (
    decorator_stable_id,
    get_node_kind,
    get_node_name,
    get_node_qualname,
)
from .node_stable_id import (
    get_stable_id as _get_stable_id_from_node,
    logical_source_from_module,
    strip_inline_node_id_lines_from_source,
)
from .tree_stable_data import (
    _STATEMENT_STABLE_TYPES,
    build_statement_stable_key,
    normalized_source_span,
)
from .tree_sidecar import (
    aliases_from_payload,
    metadata_map_from_payload,
    persisted_node_ids_from_payload,
    read_sidecar_payload,
    sidecar_matches_built_tree,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)

logger = logging.getLogger(__name__)


def _read_logical_py_source_sync_disk(py_path: Path) -> Tuple[str, PersistedNodeIds]:
    """Read Python source, strip persisted node-id markers, write disk if needed.

    Call before ``cst.parse_module`` so on-disk bytes match the logical source used
    for SHA snapshots (same policy as ``load_file_to_tree`` / save preflight).
    """
    raw = py_path.read_text(encoding="utf-8")
    logical, ids = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    if logical != raw:
        py_path.write_text(logical, encoding="utf-8")
    return logical, ids


def _attach_disk_snapshot(tree: CSTTree, source: str) -> None:
    """Record SHA256 + length of logical source (no ``# @node-id`` markers) on tree."""
    logical = strip_inline_node_id_lines_from_source(source)
    source_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(source_bytes).hexdigest()
    tree.disk_source_sha256_hex = digest
    tree.disk_source_length = len(source_bytes)
    tree.module_source_sha256_hex = digest


def _on_disk_logical_matches_tree_snapshot(path: Path, tree: CSTTree) -> bool:
    """Return True when on-disk logical Python matches the tree's disk snapshot or module.

    Uses the same logical pipeline as ``load_file_to_tree`` / ``_attach_disk_snapshot``
    (strip markers, then UTF-8 SHA256 + length). When ``disk_source_sha256_hex`` is set,
    compares to that snapshot; otherwise compares on-disk logical bytes to
    ``tree.module.code`` (in-memory-only sessions).
    """
    if not path.is_file():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    logical, _ = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    logical_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(logical_bytes).hexdigest()
    length = len(logical_bytes)
    snap = tree.disk_source_sha256_hex
    if snap is not None:
        return digest == snap and length == tree.disk_source_length
    mod_bytes = logical_source_from_module(tree.module).encode("utf-8")
    return digest == hashlib.sha256(mod_bytes).hexdigest() and length == len(mod_bytes)


def _strip_legacy_trailer_from_disk(py_path: Path, logical_source: str) -> None:
    """Atomically overwrite py_path with logical_source if the file still contains
    a legacy # cst-node-ids block (raw != logical). Safe: writes to .tmp then os.replace.
    """
    try:
        tmp_path = py_path.with_suffix(".py.tmp")
        tmp_path.write_text(logical_source, encoding="utf-8")
        os.replace(str(tmp_path), str(py_path))
        logger.info("Stripped legacy cst-node-ids trailer from %s", py_path)
    except OSError as exc:
        logger.warning("Could not strip legacy trailer from %s: %s", py_path, exc)


def _finalize_cst_tree(
    tree: CSTTree,
    module: cst.Module,
    logical_source: str,
    *,
    py_path: Optional[Path],
    raw_disk_source: Optional[str],
    node_types: Optional[List[str]],
    max_depth: Optional[int],
    include_children: bool,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]],
    legacy_persisted: PersistedNodeIds,
    write_sidecar: bool,
) -> None:
    """
    Parse-time CST index: try ``.cst/*.tree`` sidecar when SHA matches; else full
    ``_build_tree_index`` (legacy marker path map + optional previous metadata).
    """
    tree.module = module

    if py_path is not None:
        payload = read_sidecar_payload(py_path)
        if payload is not None and verify_sidecar_against_source(
            logical_source, payload
        ):
            order_raw = payload.get("metadata_node_order")
            meta_order = (
                [str(x) for x in order_raw] if isinstance(order_raw, list) else None
            )
            prev_side = metadata_map_from_payload(
                payload.get("metadata_map", {}),
                meta_order,
            )
            persisted_side = persisted_node_ids_from_payload(payload)
            if prev_side and persisted_side:
                tree.node_map.clear()
                tree.metadata_map.clear()
                tree.parent_map.clear()
                tree.node_id_aliases.clear()
                _build_tree_index(
                    tree,
                    node_types=node_types,
                    max_depth=max_depth,
                    include_children=include_children,
                    previous_metadata_map=prev_side,
                    persisted_node_ids=persisted_side,
                )
                if sidecar_matches_built_tree(tree, payload):
                    tree.node_id_aliases = aliases_from_payload(payload)
                    if raw_disk_source is not None:
                        # SHA must match logical source (no inline/legacy markers)
                        _attach_disk_snapshot(tree, logical_source)
                        # Strip inline/legacy markers from disk unconditionally
                        if raw_disk_source != logical_source and py_path is not None:
                            _strip_legacy_trailer_from_disk(py_path, logical_source)
                    return
                tree.module = cst.parse_module(logical_source)

    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    if previous_metadata_map is None:
        tree.node_id_aliases.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=legacy_persisted or None,
    )
    if raw_disk_source is not None:
        # SHA must match logical source (no inline/legacy markers)
        _attach_disk_snapshot(tree, logical_source)
        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)
        if raw_disk_source != logical_source and py_path is not None:
            _strip_legacy_trailer_from_disk(py_path, logical_source)
    if write_sidecar and py_path is not None:
        try:
            write_sidecar_atomic(py_path, tree)
        except OSError as exc:
            logger.warning("Could not write CST sidecar for %s: %s", py_path, exc)


# In-memory storage for CST trees
_trees: dict[str, CSTTree] = {}


def load_file_to_tree(
    file_path: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Load file into CST tree and store in memory.

    Args:
        file_path: Path to Python file
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    is_py = path.suffix == ".py"
    is_py_tmp = path.suffix == ".tmp" and path.stem.endswith(".py")
    if not is_py and not is_py_tmp:
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    tree = CSTTree.create(str(path.resolve()), module)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    _trees[tree.tree_id] = tree
    return tree


def create_tree_from_code(
    file_path: str,
    source_code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    *,
    persist_sidecar: bool = False,
    register_in_memory: bool = True,
) -> CSTTree:
    """
    Create CST tree from source code string (without reading from file).

    This is useful for creating trees from code that doesn't exist on disk yet.

    Args:
        file_path: Path where file will be saved (used for tree metadata)
        source_code: Python source code string
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata
        persist_sidecar: When True and ``file_path`` exists on disk, write ``.cst`` sidecar
            after indexing (used by DB sync / indexer).
        register_in_memory: When False, the tree is not stored in the global ``_trees`` map
            (used when the caller only needs a throwaway CST for one RPC).

    Returns:
        CSTTree with tree_id and metadata
    """
    logical_source, persisted_node_ids = strip_persisted_node_ids(source_code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    module = cst.parse_module(logical_source)

    tree = CSTTree.create(str(Path(file_path).resolve()), module)
    py_path = Path(file_path).resolve()
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=py_path,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=bool(persist_sidecar),
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0

    if register_in_memory:
        _trees[tree.tree_id] = tree
    return tree


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
    persisted_node_ids: Optional[PersistedNodeIds] = None,
    pinned_node_id: Optional[str] = None,
    obj_to_stable: Optional[Dict[Any, str]] = None,
) -> None:
    """
    Build node index and metadata for tree.

    ``stable_id`` lives in ``TreeNodeMetadata`` (sidecar JSON). After mutation,
    it is carried over via semantic keys (qualname, statement text), not coordinates.
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    exact_key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    if previous_metadata_map:
        for key, node_id in build_exact_key_to_id_from_metadata(
            previous_metadata_map
        ).items():
            exact_key_to_id.setdefault(key, node_id)
    class_stack: List[str] = []
    func_stack: List[str] = []
    node_to_uuid: Dict[int, str] = {}

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        if max_depth is not None and depth > max_depth:
            return

        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            if depth > 0:
                for child_index, child in enumerate(node.children):
                    visit(child, depth + 1, path_indices + (child_index,))
                return

        pos = positions.get(node)
        if pos is None and isinstance(node, cst.Decorator):
            pos = positions.get(node.decorator)
        if pos is None:
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            return

        parent = parents.get(node)

        node_id: Optional[str] = None
        marker_path = build_marker_path(path_indices)
        exact_key = build_exact_node_key(
            start_line,
            start_col,
            end_line,
            end_col,
            node_type,
        )
        if persisted_node_ids and marker_path in persisted_node_ids:
            node_id = persisted_node_ids[marker_path]
        elif exact_key in exact_key_to_id:
            node_id = exact_key_to_id.pop(exact_key)
        elif (
            pinned_node_id
            and previous_metadata_map
            and pinned_node_id in previous_metadata_map
        ):
            pin_meta = previous_metadata_map[pinned_node_id]
            if (
                node_type == pin_meta.type
                and start_line == pin_meta.start_line
                and start_col == pin_meta.start_col
            ):
                node_id = pinned_node_id
        if node_id is None:
            node_id = str(uuid.uuid4())
        node_to_uuid[id(node)] = node_id

        tree.node_map[node_id] = node
        parent_id = node_to_uuid.get(id(parent)) if parent else None
        tree.parent_map[node_id] = parent_id

        name = get_node_name(node)
        qualname = get_node_qualname(node, class_stack, func_stack)
        kind = get_node_kind(node, class_stack)
        prev_meta = (
            previous_metadata_map.get(node_id) if previous_metadata_map else None
        )
        if prev_meta is not None and (
            prev_meta.name != name or prev_meta.type != node_type
        ):
            prev_meta = None
        carried_stable_id = _get_stable_id_from_node(node)
        if node_type in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            stable_id = (
                carried_stable_id
                or (
                    obj_to_stable.get(("qualname", qualname))
                    if obj_to_stable and qualname
                    else None
                )
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        else:
            stmt_sk = None
            if obj_to_stable and node_type in _STATEMENT_STABLE_TYPES:
                norm = normalized_source_span(tree.module, start_line, end_line)
                if norm:
                    stmt_sk = build_statement_stable_key(node_type, qualname, norm)
            stable_id = (
                carried_stable_id
                or (obj_to_stable.get(stmt_sk) if stmt_sk else None)
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        if isinstance(node, cst.Decorator):
            parent_cst = parents.get(node)
            if isinstance(parent_cst, (cst.FunctionDef, cst.ClassDef)):
                dec_index = next(
                    (i for i, d in enumerate(parent_cst.decorators) if d is node),
                    0,
                )
                parent_qual = get_node_qualname(parent_cst, class_stack, func_stack)
                if not prev_meta or not prev_meta.stable_id:
                    stable_id = decorator_stable_id(parent_qual, dec_index)

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        children_ids = (
            [node_to_uuid[id(c)] for c in node.children if id(c) in node_to_uuid]
            if include_children
            else []
        )

        metadata = TreeNodeMetadata(
            node_id=node_id,
            stable_id=stable_id,
            type=node_type,
            kind=kind,
            name=name,
            qualname=qualname,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            children_count=len(children_ids),
            children_ids=children_ids,
            parent_id=parent_id,
        )
        tree.metadata_map[node_id] = metadata
        if depth == 0:
            tree.root_node_id = node_id

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0, (0,))


def get_tree(tree_id: str) -> Optional[CSTTree]:
    """Return the in-memory CST tree, refreshing from disk when the file drifted.

    When ``disk_source_sha256_hex`` / ``disk_source_length`` were set at load time
    and the on-disk logical ``.py`` no longer matches that snapshot, the tree is
    rebuilt from disk (via :func:`reload_tree_from_file`) so ``stable_id`` / index
    state match the file. Trees without a disk snapshot (e.g. rollback-only
    in-memory state) are returned as-is.
    """
    tree = _trees.get(tree_id)
    if tree is None:
        return None
    tree.last_accessed_at = time.monotonic()
    path = Path(tree.file_path)
    snap = tree.disk_source_sha256_hex
    if snap is None or not path.is_file():
        return tree
    mod_snap = tree.module_source_sha256_hex
    if mod_snap is not None and mod_snap != snap:
        # Unsaved in-memory edits (e.g. universal_file_edit); do not reload from disk.
        return tree
    if _on_disk_logical_matches_tree_snapshot(path, tree):
        return tree
    reloaded = reload_tree_from_file(tree_id)
    return reloaded if reloaded is not None else tree


def remove_tree(tree_id: str) -> bool:
    """Remove tree from memory."""
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(
    tree_id: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> Optional[CSTTree]:
    """
    Reload tree from file, updating existing tree in memory.

    When the on-disk logical source still matches the tree's disk snapshot (and the
    caller uses default index parameters), returns the existing tree without
    reparsing or rebuilding the index. Otherwise reads the file, reparses, and
    runs a full index rebuild (``node_id_aliases`` are cleared on that path).

    The tree_id remains the same, so all references to the tree remain valid.

    Args:
        tree_id: Existing tree ID to update
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        Updated CSTTree or None if tree not found

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file is not a Python file
    """
    tree = _trees.get(tree_id)
    if not tree:
        return None

    # Read and parse file
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {tree.file_path}")

    default_index_params = (
        node_types is None and max_depth is None and include_children is True
    )
    if default_index_params and _on_disk_logical_matches_tree_snapshot(path, tree):
        tree.last_accessed_at = time.monotonic()
        return tree

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    previous_metadata_map = dict(tree.metadata_map)

    # Update tree in place
    tree.file_path = str(path.resolve())

    # Clear aliases before reload; sidecar or rebuild will repopulate if needed
    tree.node_id_aliases.clear()

    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    return tree


def rollback_tree_to_code(
    tree_id: str,
    code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    index_metadata_for_code: Optional[Dict[str, TreeNodeMetadata]] = None,
) -> bool:
    """
    Restore in-memory tree to the given source code (rollback after failed save).

    Replaces tree.module with parsed code and rebuilds index. Use when save
    fails after modify so the tree is reverted to pre-modify state.

    Disk snapshot fields (``disk_source_sha256_hex``, ``disk_source_length``) and
    ``module_source_sha256_hex`` are cleared: rollback reflects in-memory code only,
    not the file on disk, so save-side disk verification must not run against a stale
    snapshot until ``reload_tree_from_file`` / equivalent reload from disk.

    Args:
        tree_id: Tree ID to roll back
        code: Full module source code to restore
        node_types: Optional filter for index (same as load)
        max_depth: Optional max depth for index
        include_children: Whether to index children
        index_metadata_for_code: Optional snapshot of ``metadata_map`` that matches
            ``code`` (e.g. ``dict(tree.metadata_map)`` taken before ``modify_tree``).
            When provided, node_id stability is preserved across rollback; when omitted,
            the current in-memory map is used (legacy behavior).

    Returns:
        True if tree was found and rolled back, False if tree not found
    """
    tree = _trees.get(tree_id)
    if not tree:
        return False
    logical_source, persisted_node_ids = strip_persisted_node_ids(code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    # Must use metadata for the same source as ``code`` (typically pre-mutate
    # snapshot). Using the current tree.metadata_map after a failed or preview
    # mutate rebuilds UUIDs incorrectly and invalidates node_id stability.
    if index_metadata_for_code is not None:
        previous_metadata_map = index_metadata_for_code
    else:
        previous_metadata_map = dict(tree.metadata_map)
    module = cst.parse_module(logical_source)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=None,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=False,
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0
    # modify_tree updates module_source_sha256_hex; rollback must not leave a stale
    # digest that no longer matches tree.module.code (e.g. cst_modify_tree preview).
    tree.module_source_sha256_hex = None
    return True


CST_TREE_TTL_SECONDS: float = 900.0  # 15 minutes


async def _cst_tree_ttl_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [
            tid
            for tid, t in list(_trees.items())
            if (now - t.last_accessed_at) > CST_TREE_TTL_SECONDS
        ]
        for tid in expired:
            _trees.pop(tid, None)


def start_cst_tree_ttl_cleanup() -> None:
    asyncio.ensure_future(_cst_tree_ttl_cleanup_loop())
```



## G-000/T-003/A-010 post-impl proxy (docstrings fixed)

**Target:** `code_analysis/core/cst_tree/tree_builder.py`  
**Baseline line count:** 704  
Post-A-010 implementation (docstring-only). Same line count as baseline.

```python
"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_key_to_id_from_metadata,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from .node_type_utils import (
    decorator_stable_id,
    get_node_kind,
    get_node_name,
    get_node_qualname,
)
from .node_stable_id import (
    get_stable_id as _get_stable_id_from_node,
    logical_source_from_module,
    strip_inline_node_id_lines_from_source,
)
from .tree_stable_data import (
    _STATEMENT_STABLE_TYPES,
    build_statement_stable_key,
    normalized_source_span,
)
from .tree_sidecar import (
    aliases_from_payload,
    metadata_map_from_payload,
    persisted_node_ids_from_payload,
    read_sidecar_payload,
    sidecar_matches_built_tree,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)

logger = logging.getLogger(__name__)


def _read_logical_py_source_sync_disk(py_path: Path) -> Tuple[str, PersistedNodeIds]:
    """Read Python source, strip persisted node-id markers, write disk if needed.

    Call before ``cst.parse_module`` so on-disk bytes match the logical source used
    for SHA snapshots (same policy as ``load_file_to_tree`` / save preflight).
    """
    raw = py_path.read_text(encoding="utf-8")
    logical, ids = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    if logical != raw:
        py_path.write_text(logical, encoding="utf-8")
    return logical, ids


def _attach_disk_snapshot(tree: CSTTree, source: str) -> None:
    """Record SHA256 + length of logical source (no ``# @node-id`` markers) on tree."""
    logical = strip_inline_node_id_lines_from_source(source)
    source_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(source_bytes).hexdigest()
    tree.disk_source_sha256_hex = digest
    tree.disk_source_length = len(source_bytes)
    tree.module_source_sha256_hex = digest


def _on_disk_logical_matches_tree_snapshot(path: Path, tree: CSTTree) -> bool:
    """Return True when on-disk logical Python matches the tree's disk snapshot or module.

    Uses the same logical pipeline as ``load_file_to_tree`` / ``_attach_disk_snapshot``
    (strip markers, then UTF-8 SHA256 + length). When ``disk_source_sha256_hex`` is set,
    compares to that snapshot; otherwise compares on-disk logical bytes to
    ``tree.module.code`` (in-memory-only sessions).
    """
    if not path.is_file():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    logical, _ = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    logical_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(logical_bytes).hexdigest()
    length = len(logical_bytes)
    snap = tree.disk_source_sha256_hex
    if snap is not None:
        return digest == snap and length == tree.disk_source_length
    mod_bytes = logical_source_from_module(tree.module).encode("utf-8")
    return digest == hashlib.sha256(mod_bytes).hexdigest() and length == len(mod_bytes)


def _strip_legacy_trailer_from_disk(py_path: Path, logical_source: str) -> None:
    """Atomically overwrite py_path with logical_source if the file still contains
    a legacy # cst-node-ids block (raw != logical). Safe: writes to .tmp then os.replace.
    """
    try:
        tmp_path = py_path.with_suffix(".py.tmp")
        tmp_path.write_text(logical_source, encoding="utf-8")
        os.replace(str(tmp_path), str(py_path))
        logger.info("Stripped legacy cst-node-ids trailer from %s", py_path)
    except OSError as exc:
        logger.warning("Could not strip legacy trailer from %s: %s", py_path, exc)


def _finalize_cst_tree(
    tree: CSTTree,
    module: cst.Module,
    logical_source: str,
    *,
    py_path: Optional[Path],
    raw_disk_source: Optional[str],
    node_types: Optional[List[str]],
    max_depth: Optional[int],
    include_children: bool,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]],
    legacy_persisted: PersistedNodeIds,
    write_sidecar: bool,
) -> None:
    """
    Parse-time CST index: try the sibling ``<source>.py.tree`` sidecar when SHA matches; else full
    ``_build_tree_index`` (legacy marker path map + optional previous metadata).
    """
    tree.module = module

    if py_path is not None:
        payload = read_sidecar_payload(py_path)
        if payload is not None and verify_sidecar_against_source(
            logical_source, payload
        ):
            order_raw = payload.get("metadata_node_order")
            meta_order = (
                [str(x) for x in order_raw] if isinstance(order_raw, list) else None
            )
            prev_side = metadata_map_from_payload(
                payload.get("metadata_map", {}),
                meta_order,
            )
            persisted_side = persisted_node_ids_from_payload(payload)
            if prev_side and persisted_side:
                tree.node_map.clear()
                tree.metadata_map.clear()
                tree.parent_map.clear()
                tree.node_id_aliases.clear()
                _build_tree_index(
                    tree,
                    node_types=node_types,
                    max_depth=max_depth,
                    include_children=include_children,
                    previous_metadata_map=prev_side,
                    persisted_node_ids=persisted_side,
                )
                if sidecar_matches_built_tree(tree, payload):
                    tree.node_id_aliases = aliases_from_payload(payload)
                    if raw_disk_source is not None:
                        # SHA must match logical source (no inline/legacy markers)
                        _attach_disk_snapshot(tree, logical_source)
                        # Strip inline/legacy markers from disk unconditionally
                        if raw_disk_source != logical_source and py_path is not None:
                            _strip_legacy_trailer_from_disk(py_path, logical_source)
                    return
                tree.module = cst.parse_module(logical_source)

    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    if previous_metadata_map is None:
        tree.node_id_aliases.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=legacy_persisted or None,
    )
    if raw_disk_source is not None:
        # SHA must match logical source (no inline/legacy markers)
        _attach_disk_snapshot(tree, logical_source)
        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)
        if raw_disk_source != logical_source and py_path is not None:
            _strip_legacy_trailer_from_disk(py_path, logical_source)
    if write_sidecar and py_path is not None:
        try:
            write_sidecar_atomic(py_path, tree)
        except OSError as exc:
            logger.warning("Could not write CST sidecar for %s: %s", py_path, exc)


# In-memory storage for CST trees
_trees: dict[str, CSTTree] = {}


def load_file_to_tree(
    file_path: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Load file into CST tree and store in memory.

    Args:
        file_path: Path to Python file
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    is_py = path.suffix == ".py"
    is_py_tmp = path.suffix == ".tmp" and path.stem.endswith(".py")
    if not is_py and not is_py_tmp:
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    tree = CSTTree.create(str(path.resolve()), module)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    _trees[tree.tree_id] = tree
    return tree


def create_tree_from_code(
    file_path: str,
    source_code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    *,
    persist_sidecar: bool = False,
    register_in_memory: bool = True,
) -> CSTTree:
    """
    Create CST tree from source code string (without reading from file).

    This is useful for creating trees from code that doesn't exist on disk yet.

    Args:
        file_path: Path where file will be saved (used for tree metadata)
        source_code: Python source code string
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata
        persist_sidecar: When True and ``file_path`` exists on disk, write the sibling
            ``<source>.py.tree`` sidecar after indexing (used by DB sync / indexer).
        register_in_memory: When False, the tree is not stored in the global ``_trees`` map
            (used when the caller only needs a throwaway CST for one RPC).

    Returns:
        CSTTree with tree_id and metadata
    """
    logical_source, persisted_node_ids = strip_persisted_node_ids(source_code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    module = cst.parse_module(logical_source)

    tree = CSTTree.create(str(Path(file_path).resolve()), module)
    py_path = Path(file_path).resolve()
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=py_path,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=bool(persist_sidecar),
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0

    if register_in_memory:
        _trees[tree.tree_id] = tree
    return tree


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
    persisted_node_ids: Optional[PersistedNodeIds] = None,
    pinned_node_id: Optional[str] = None,
    obj_to_stable: Optional[Dict[Any, str]] = None,
) -> None:
    """
    Build node index and metadata for tree.

    ``stable_id`` lives in ``TreeNodeMetadata`` (sidecar JSON). After mutation,
    it is carried over via semantic keys (qualname, statement text), not coordinates.
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    exact_key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    if previous_metadata_map:
        for key, node_id in build_exact_key_to_id_from_metadata(
            previous_metadata_map
        ).items():
            exact_key_to_id.setdefault(key, node_id)
    class_stack: List[str] = []
    func_stack: List[str] = []
    node_to_uuid: Dict[int, str] = {}

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        if max_depth is not None and depth > max_depth:
            return

        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            if depth > 0:
                for child_index, child in enumerate(node.children):
                    visit(child, depth + 1, path_indices + (child_index,))
                return

        pos = positions.get(node)
        if pos is None and isinstance(node, cst.Decorator):
            pos = positions.get(node.decorator)
        if pos is None:
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            return

        parent = parents.get(node)

        node_id: Optional[str] = None
        marker_path = build_marker_path(path_indices)
        exact_key = build_exact_node_key(
            start_line,
            start_col,
            end_line,
            end_col,
            node_type,
        )
        if persisted_node_ids and marker_path in persisted_node_ids:
            node_id = persisted_node_ids[marker_path]
        elif exact_key in exact_key_to_id:
            node_id = exact_key_to_id.pop(exact_key)
        elif (
            pinned_node_id
            and previous_metadata_map
            and pinned_node_id in previous_metadata_map
        ):
            pin_meta = previous_metadata_map[pinned_node_id]
            if (
                node_type == pin_meta.type
                and start_line == pin_meta.start_line
                and start_col == pin_meta.start_col
            ):
                node_id = pinned_node_id
        if node_id is None:
            node_id = str(uuid.uuid4())
        node_to_uuid[id(node)] = node_id

        tree.node_map[node_id] = node
        parent_id = node_to_uuid.get(id(parent)) if parent else None
        tree.parent_map[node_id] = parent_id

        name = get_node_name(node)
        qualname = get_node_qualname(node, class_stack, func_stack)
        kind = get_node_kind(node, class_stack)
        prev_meta = (
            previous_metadata_map.get(node_id) if previous_metadata_map else None
        )
        if prev_meta is not None and (
            prev_meta.name != name or prev_meta.type != node_type
        ):
            prev_meta = None
        carried_stable_id = _get_stable_id_from_node(node)
        if node_type in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            stable_id = (
                carried_stable_id
                or (
                    obj_to_stable.get(("qualname", qualname))
                    if obj_to_stable and qualname
                    else None
                )
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        else:
            stmt_sk = None
            if obj_to_stable and node_type in _STATEMENT_STABLE_TYPES:
                norm = normalized_source_span(tree.module, start_line, end_line)
                if norm:
                    stmt_sk = build_statement_stable_key(node_type, qualname, norm)
            stable_id = (
                carried_stable_id
                or (obj_to_stable.get(stmt_sk) if stmt_sk else None)
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        if isinstance(node, cst.Decorator):
            parent_cst = parents.get(node)
            if isinstance(parent_cst, (cst.FunctionDef, cst.ClassDef)):
                dec_index = next(
                    (i for i, d in enumerate(parent_cst.decorators) if d is node),
                    0,
                )
                parent_qual = get_node_qualname(parent_cst, class_stack, func_stack)
                if not prev_meta or not prev_meta.stable_id:
                    stable_id = decorator_stable_id(parent_qual, dec_index)

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        children_ids = (
            [node_to_uuid[id(c)] for c in node.children if id(c) in node_to_uuid]
            if include_children
            else []
        )

        metadata = TreeNodeMetadata(
            node_id=node_id,
            stable_id=stable_id,
            type=node_type,
            kind=kind,
            name=name,
            qualname=qualname,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            children_count=len(children_ids),
            children_ids=children_ids,
            parent_id=parent_id,
        )
        tree.metadata_map[node_id] = metadata
        if depth == 0:
            tree.root_node_id = node_id

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0, (0,))


def get_tree(tree_id: str) -> Optional[CSTTree]:
    """Return the in-memory CST tree, refreshing from disk when the file drifted.

    When ``disk_source_sha256_hex`` / ``disk_source_length`` were set at load time
    and the on-disk logical ``.py`` no longer matches that snapshot, the tree is
    rebuilt from disk (via :func:`reload_tree_from_file`) so ``stable_id`` / index
    state match the file. Trees without a disk snapshot (e.g. rollback-only
    in-memory state) are returned as-is.
    """
    tree = _trees.get(tree_id)
    if tree is None:
        return None
    tree.last_accessed_at = time.monotonic()
    path = Path(tree.file_path)
    snap = tree.disk_source_sha256_hex
    if snap is None or not path.is_file():
        return tree
    mod_snap = tree.module_source_sha256_hex
    if mod_snap is not None and mod_snap != snap:
        # Unsaved in-memory edits (e.g. universal_file_edit); do not reload from disk.
        return tree
    if _on_disk_logical_matches_tree_snapshot(path, tree):
        return tree
    reloaded = reload_tree_from_file(tree_id)
    return reloaded if reloaded is not None else tree


def remove_tree(tree_id: str) -> bool:
    """Remove tree from memory."""
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(
    tree_id: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> Optional[CSTTree]:
    """
    Reload tree from file, updating existing tree in memory.

    When the on-disk logical source still matches the tree's disk snapshot (and the
    caller uses default index parameters), returns the existing tree without
    reparsing or rebuilding the index. Otherwise reads the file, reparses, and
    runs a full index rebuild (``node_id_aliases`` are cleared on that path).

    The tree_id remains the same, so all references to the tree remain valid.

    Args:
        tree_id: Existing tree ID to update
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        Updated CSTTree or None if tree not found

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file is not a Python file
    """
    tree = _trees.get(tree_id)
    if not tree:
        return None

    # Read and parse file
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {tree.file_path}")

    default_index_params = (
        node_types is None and max_depth is None and include_children is True
    )
    if default_index_params and _on_disk_logical_matches_tree_snapshot(path, tree):
        tree.last_accessed_at = time.monotonic()
        return tree

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    previous_metadata_map = dict(tree.metadata_map)

    # Update tree in place
    tree.file_path = str(path.resolve())

    # Clear aliases before reload; sidecar or rebuild will repopulate if needed
    tree.node_id_aliases.clear()

    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    return tree


def rollback_tree_to_code(
    tree_id: str,
    code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    index_metadata_for_code: Optional[Dict[str, TreeNodeMetadata]] = None,
) -> bool:
    """
    Restore in-memory tree to the given source code (rollback after failed save).

    Replaces tree.module with parsed code and rebuilds index. Use when save
    fails after modify so the tree is reverted to pre-modify state.

    Disk snapshot fields (``disk_source_sha256_hex``, ``disk_source_length``) and
    ``module_source_sha256_hex`` are cleared: rollback reflects in-memory code only,
    not the file on disk, so save-side disk verification must not run against a stale
    snapshot until ``reload_tree_from_file`` / equivalent reload from disk.

    Args:
        tree_id: Tree ID to roll back
        code: Full module source code to restore
        node_types: Optional filter for index (same as load)
        max_depth: Optional max depth for index
        include_children: Whether to index children
        index_metadata_for_code: Optional snapshot of ``metadata_map`` that matches
            ``code`` (e.g. ``dict(tree.metadata_map)`` taken before ``modify_tree``).
            When provided, node_id stability is preserved across rollback; when omitted,
            the current in-memory map is used (legacy behavior).

    Returns:
        True if tree was found and rolled back, False if tree not found
    """
    tree = _trees.get(tree_id)
    if not tree:
        return False
    logical_source, persisted_node_ids = strip_persisted_node_ids(code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    # Must use metadata for the same source as ``code`` (typically pre-mutate
    # snapshot). Using the current tree.metadata_map after a failed or preview
    # mutate rebuilds UUIDs incorrectly and invalidates node_id stability.
    if index_metadata_for_code is not None:
        previous_metadata_map = index_metadata_for_code
    else:
        previous_metadata_map = dict(tree.metadata_map)
    module = cst.parse_module(logical_source)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=None,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=False,
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0
    # modify_tree updates module_source_sha256_hex; rollback must not leave a stale
    # digest that no longer matches tree.module.code (e.g. cst_modify_tree preview).
    tree.module_source_sha256_hex = None
    return True


CST_TREE_TTL_SECONDS: float = 900.0  # 15 minutes


async def _cst_tree_ttl_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [
            tid
            for tid, t in list(_trees.items())
            if (now - t.last_accessed_at) > CST_TREE_TTL_SECONDS
        ]
        for tid in expired:
            _trees.pop(tid, None)


def start_cst_tree_ttl_cleanup() -> None:
    asyncio.ensure_future(_cst_tree_ttl_cleanup_loop())
```




## G-000/T-003/A-012

**Target:** `code_analysis/core/cst_tree/tree_builder.py`  
**Baseline line count:** 704  
**Chain:** post A-010 docstring edits; A-011 creates `tree_builder_index.py` without modifying this file. A-012 deletes moved helpers and adds imports. Post-impl estimate: ~310–377L (simulation: 377L before unused-import cleanup).

```python
"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_key_to_id_from_metadata,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from .node_type_utils import (
    decorator_stable_id,
    get_node_kind,
    get_node_name,
    get_node_qualname,
)
from .node_stable_id import (
    get_stable_id as _get_stable_id_from_node,
    logical_source_from_module,
    strip_inline_node_id_lines_from_source,
)
from .tree_stable_data import (
    _STATEMENT_STABLE_TYPES,
    build_statement_stable_key,
    normalized_source_span,
)
from .tree_sidecar import (
    aliases_from_payload,
    metadata_map_from_payload,
    persisted_node_ids_from_payload,
    read_sidecar_payload,
    sidecar_matches_built_tree,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)

logger = logging.getLogger(__name__)


def _read_logical_py_source_sync_disk(py_path: Path) -> Tuple[str, PersistedNodeIds]:
    """Read Python source, strip persisted node-id markers, write disk if needed.

    Call before ``cst.parse_module`` so on-disk bytes match the logical source used
    for SHA snapshots (same policy as ``load_file_to_tree`` / save preflight).
    """
    raw = py_path.read_text(encoding="utf-8")
    logical, ids = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    if logical != raw:
        py_path.write_text(logical, encoding="utf-8")
    return logical, ids


def _attach_disk_snapshot(tree: CSTTree, source: str) -> None:
    """Record SHA256 + length of logical source (no ``# @node-id`` markers) on tree."""
    logical = strip_inline_node_id_lines_from_source(source)
    source_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(source_bytes).hexdigest()
    tree.disk_source_sha256_hex = digest
    tree.disk_source_length = len(source_bytes)
    tree.module_source_sha256_hex = digest


def _on_disk_logical_matches_tree_snapshot(path: Path, tree: CSTTree) -> bool:
    """Return True when on-disk logical Python matches the tree's disk snapshot or module.

    Uses the same logical pipeline as ``load_file_to_tree`` / ``_attach_disk_snapshot``
    (strip markers, then UTF-8 SHA256 + length). When ``disk_source_sha256_hex`` is set,
    compares to that snapshot; otherwise compares on-disk logical bytes to
    ``tree.module.code`` (in-memory-only sessions).
    """
    if not path.is_file():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    logical, _ = strip_persisted_node_ids(raw)
    logical = strip_inline_node_id_lines_from_source(logical)
    logical_bytes = logical.encode("utf-8")
    digest = hashlib.sha256(logical_bytes).hexdigest()
    length = len(logical_bytes)
    snap = tree.disk_source_sha256_hex
    if snap is not None:
        return digest == snap and length == tree.disk_source_length
    mod_bytes = logical_source_from_module(tree.module).encode("utf-8")
    return digest == hashlib.sha256(mod_bytes).hexdigest() and length == len(mod_bytes)


def _strip_legacy_trailer_from_disk(py_path: Path, logical_source: str) -> None:
    """Atomically overwrite py_path with logical_source if the file still contains
    a legacy # cst-node-ids block (raw != logical). Safe: writes to .tmp then os.replace.
    """
    try:
        tmp_path = py_path.with_suffix(".py.tmp")
        tmp_path.write_text(logical_source, encoding="utf-8")
        os.replace(str(tmp_path), str(py_path))
        logger.info("Stripped legacy cst-node-ids trailer from %s", py_path)
    except OSError as exc:
        logger.warning("Could not strip legacy trailer from %s: %s", py_path, exc)


def _finalize_cst_tree(
    tree: CSTTree,
    module: cst.Module,
    logical_source: str,
    *,
    py_path: Optional[Path],
    raw_disk_source: Optional[str],
    node_types: Optional[List[str]],
    max_depth: Optional[int],
    include_children: bool,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]],
    legacy_persisted: PersistedNodeIds,
    write_sidecar: bool,
) -> None:
    """
    Parse-time CST index: try the sibling ``<source>.py.tree`` sidecar when SHA matches; else full
    ``_build_tree_index`` (legacy marker path map + optional previous metadata).
    """
    tree.module = module

    if py_path is not None:
        payload = read_sidecar_payload(py_path)
        if payload is not None and verify_sidecar_against_source(
            logical_source, payload
        ):
            order_raw = payload.get("metadata_node_order")
            meta_order = (
                [str(x) for x in order_raw] if isinstance(order_raw, list) else None
            )
            prev_side = metadata_map_from_payload(
                payload.get("metadata_map", {}),
                meta_order,
            )
            persisted_side = persisted_node_ids_from_payload(payload)
            if prev_side and persisted_side:
                tree.node_map.clear()
                tree.metadata_map.clear()
                tree.parent_map.clear()
                tree.node_id_aliases.clear()
                _build_tree_index(
                    tree,
                    node_types=node_types,
                    max_depth=max_depth,
                    include_children=include_children,
                    previous_metadata_map=prev_side,
                    persisted_node_ids=persisted_side,
                )
                if sidecar_matches_built_tree(tree, payload):
                    tree.node_id_aliases = aliases_from_payload(payload)
                    if raw_disk_source is not None:
                        # SHA must match logical source (no inline/legacy markers)
                        _attach_disk_snapshot(tree, logical_source)
                        # Strip inline/legacy markers from disk unconditionally
                        if raw_disk_source != logical_source and py_path is not None:
                            _strip_legacy_trailer_from_disk(py_path, logical_source)
                    return
                tree.module = cst.parse_module(logical_source)

    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    if previous_metadata_map is None:
        tree.node_id_aliases.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=legacy_persisted or None,
    )
    if raw_disk_source is not None:
        # SHA must match logical source (no inline/legacy markers)
        _attach_disk_snapshot(tree, logical_source)
        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)
        if raw_disk_source != logical_source and py_path is not None:
            _strip_legacy_trailer_from_disk(py_path, logical_source)
    if write_sidecar and py_path is not None:
        try:
            write_sidecar_atomic(py_path, tree)
        except OSError as exc:
            logger.warning("Could not write CST sidecar for %s: %s", py_path, exc)


# In-memory storage for CST trees
_trees: dict[str, CSTTree] = {}


def load_file_to_tree(
    file_path: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Load file into CST tree and store in memory.

    Args:
        file_path: Path to Python file
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    is_py = path.suffix == ".py"
    is_py_tmp = path.suffix == ".tmp" and path.stem.endswith(".py")
    if not is_py and not is_py_tmp:
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    tree = CSTTree.create(str(path.resolve()), module)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    _trees[tree.tree_id] = tree
    return tree


def create_tree_from_code(
    file_path: str,
    source_code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    *,
    persist_sidecar: bool = False,
    register_in_memory: bool = True,
) -> CSTTree:
    """
    Create CST tree from source code string (without reading from file).

    This is useful for creating trees from code that doesn't exist on disk yet.

    Args:
        file_path: Path where file will be saved (used for tree metadata)
        source_code: Python source code string
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata
        persist_sidecar: When True and ``file_path`` exists on disk, write the sibling
            ``<source>.py.tree`` sidecar after indexing (used by DB sync / indexer).
        register_in_memory: When False, the tree is not stored in the global ``_trees`` map
            (used when the caller only needs a throwaway CST for one RPC).

    Returns:
        CSTTree with tree_id and metadata
    """
    logical_source, persisted_node_ids = strip_persisted_node_ids(source_code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    module = cst.parse_module(logical_source)

    tree = CSTTree.create(str(Path(file_path).resolve()), module)
    py_path = Path(file_path).resolve()
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=py_path,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=None,
        legacy_persisted=persisted_node_ids,
        write_sidecar=bool(persist_sidecar),
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0

    if register_in_memory:
        _trees[tree.tree_id] = tree
    return tree


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
    persisted_node_ids: Optional[PersistedNodeIds] = None,
    pinned_node_id: Optional[str] = None,
    obj_to_stable: Optional[Dict[Any, str]] = None,
) -> None:
    """
    Build node index and metadata for tree.

    ``stable_id`` lives in ``TreeNodeMetadata`` (sidecar JSON). After mutation,
    it is carried over via semantic keys (qualname, statement text), not coordinates.
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    exact_key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    if previous_metadata_map:
        for key, node_id in build_exact_key_to_id_from_metadata(
            previous_metadata_map
        ).items():
            exact_key_to_id.setdefault(key, node_id)
    class_stack: List[str] = []
    func_stack: List[str] = []
    node_to_uuid: Dict[int, str] = {}

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        if max_depth is not None and depth > max_depth:
            return

        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            if depth > 0:
                for child_index, child in enumerate(node.children):
                    visit(child, depth + 1, path_indices + (child_index,))
                return

        pos = positions.get(node)
        if pos is None and isinstance(node, cst.Decorator):
            pos = positions.get(node.decorator)
        if pos is None:
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            return

        parent = parents.get(node)

        node_id: Optional[str] = None
        marker_path = build_marker_path(path_indices)
        exact_key = build_exact_node_key(
            start_line,
            start_col,
            end_line,
            end_col,
            node_type,
        )
        if persisted_node_ids and marker_path in persisted_node_ids:
            node_id = persisted_node_ids[marker_path]
        elif exact_key in exact_key_to_id:
            node_id = exact_key_to_id.pop(exact_key)
        elif (
            pinned_node_id
            and previous_metadata_map
            and pinned_node_id in previous_metadata_map
        ):
            pin_meta = previous_metadata_map[pinned_node_id]
            if (
                node_type == pin_meta.type
                and start_line == pin_meta.start_line
                and start_col == pin_meta.start_col
            ):
                node_id = pinned_node_id
        if node_id is None:
            node_id = str(uuid.uuid4())
        node_to_uuid[id(node)] = node_id

        tree.node_map[node_id] = node
        parent_id = node_to_uuid.get(id(parent)) if parent else None
        tree.parent_map[node_id] = parent_id

        name = get_node_name(node)
        qualname = get_node_qualname(node, class_stack, func_stack)
        kind = get_node_kind(node, class_stack)
        prev_meta = (
            previous_metadata_map.get(node_id) if previous_metadata_map else None
        )
        if prev_meta is not None and (
            prev_meta.name != name or prev_meta.type != node_type
        ):
            prev_meta = None
        carried_stable_id = _get_stable_id_from_node(node)
        if node_type in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            stable_id = (
                carried_stable_id
                or (
                    obj_to_stable.get(("qualname", qualname))
                    if obj_to_stable and qualname
                    else None
                )
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        else:
            stmt_sk = None
            if obj_to_stable and node_type in _STATEMENT_STABLE_TYPES:
                norm = normalized_source_span(tree.module, start_line, end_line)
                if norm:
                    stmt_sk = build_statement_stable_key(node_type, qualname, norm)
            stable_id = (
                carried_stable_id
                or (obj_to_stable.get(stmt_sk) if stmt_sk else None)
                or (prev_meta.stable_id if prev_meta else None)
                or node_id
            )
        if isinstance(node, cst.Decorator):
            parent_cst = parents.get(node)
            if isinstance(parent_cst, (cst.FunctionDef, cst.ClassDef)):
                dec_index = next(
                    (i for i, d in enumerate(parent_cst.decorators) if d is node),
                    0,
                )
                parent_qual = get_node_qualname(parent_cst, class_stack, func_stack)
                if not prev_meta or not prev_meta.stable_id:
                    stable_id = decorator_stable_id(parent_qual, dec_index)

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        children_ids = (
            [node_to_uuid[id(c)] for c in node.children if id(c) in node_to_uuid]
            if include_children
            else []
        )

        metadata = TreeNodeMetadata(
            node_id=node_id,
            stable_id=stable_id,
            type=node_type,
            kind=kind,
            name=name,
            qualname=qualname,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            children_count=len(children_ids),
            children_ids=children_ids,
            parent_id=parent_id,
        )
        tree.metadata_map[node_id] = metadata
        if depth == 0:
            tree.root_node_id = node_id

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0, (0,))


def get_tree(tree_id: str) -> Optional[CSTTree]:
    """Return the in-memory CST tree, refreshing from disk when the file drifted.

    When ``disk_source_sha256_hex`` / ``disk_source_length`` were set at load time
    and the on-disk logical ``.py`` no longer matches that snapshot, the tree is
    rebuilt from disk (via :func:`reload_tree_from_file`) so ``stable_id`` / index
    state match the file. Trees without a disk snapshot (e.g. rollback-only
    in-memory state) are returned as-is.
    """
    tree = _trees.get(tree_id)
    if tree is None:
        return None
    tree.last_accessed_at = time.monotonic()
    path = Path(tree.file_path)
    snap = tree.disk_source_sha256_hex
    if snap is None or not path.is_file():
        return tree
    mod_snap = tree.module_source_sha256_hex
    if mod_snap is not None and mod_snap != snap:
        # Unsaved in-memory edits (e.g. universal_file_edit); do not reload from disk.
        return tree
    if _on_disk_logical_matches_tree_snapshot(path, tree):
        return tree
    reloaded = reload_tree_from_file(tree_id)
    return reloaded if reloaded is not None else tree


def remove_tree(tree_id: str) -> bool:
    """Remove tree from memory."""
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(
    tree_id: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> Optional[CSTTree]:
    """
    Reload tree from file, updating existing tree in memory.

    When the on-disk logical source still matches the tree's disk snapshot (and the
    caller uses default index parameters), returns the existing tree without
    reparsing or rebuilding the index. Otherwise reads the file, reparses, and
    runs a full index rebuild (``node_id_aliases`` are cleared on that path).

    The tree_id remains the same, so all references to the tree remain valid.

    Args:
        tree_id: Existing tree ID to update
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        Updated CSTTree or None if tree not found

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file is not a Python file
    """
    tree = _trees.get(tree_id)
    if not tree:
        return None

    # Read and parse file
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {tree.file_path}")

    default_index_params = (
        node_types is None and max_depth is None and include_children is True
    )
    if default_index_params and _on_disk_logical_matches_tree_snapshot(path, tree):
        tree.last_accessed_at = time.monotonic()
        return tree

    logical_source, persisted_node_ids = _read_logical_py_source_sync_disk(path)
    module = cst.parse_module(logical_source)
    previous_metadata_map = dict(tree.metadata_map)

    # Update tree in place
    tree.file_path = str(path.resolve())

    # Clear aliases before reload; sidecar or rebuild will repopulate if needed
    tree.node_id_aliases.clear()

    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=path,
        raw_disk_source=logical_source,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=True,
    )

    return tree


def rollback_tree_to_code(
    tree_id: str,
    code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    index_metadata_for_code: Optional[Dict[str, TreeNodeMetadata]] = None,
) -> bool:
    """
    Restore in-memory tree to the given source code (rollback after failed save).

    Replaces tree.module with parsed code and rebuilds index. Use when save
    fails after modify so the tree is reverted to pre-modify state.

    Disk snapshot fields (``disk_source_sha256_hex``, ``disk_source_length``) and
    ``module_source_sha256_hex`` are cleared: rollback reflects in-memory code only,
    not the file on disk, so save-side disk verification must not run against a stale
    snapshot until ``reload_tree_from_file`` / equivalent reload from disk.

    Args:
        tree_id: Tree ID to roll back
        code: Full module source code to restore
        node_types: Optional filter for index (same as load)
        max_depth: Optional max depth for index
        include_children: Whether to index children
        index_metadata_for_code: Optional snapshot of ``metadata_map`` that matches
            ``code`` (e.g. ``dict(tree.metadata_map)`` taken before ``modify_tree``).
            When provided, node_id stability is preserved across rollback; when omitted,
            the current in-memory map is used (legacy behavior).

    Returns:
        True if tree was found and rolled back, False if tree not found
    """
    tree = _trees.get(tree_id)
    if not tree:
        return False
    logical_source, persisted_node_ids = strip_persisted_node_ids(code)
    logical_source = strip_inline_node_id_lines_from_source(logical_source)
    # Must use metadata for the same source as ``code`` (typically pre-mutate
    # snapshot). Using the current tree.metadata_map after a failed or preview
    # mutate rebuilds UUIDs incorrectly and invalidates node_id stability.
    if index_metadata_for_code is not None:
        previous_metadata_map = index_metadata_for_code
    else:
        previous_metadata_map = dict(tree.metadata_map)
    module = cst.parse_module(logical_source)
    _finalize_cst_tree(
        tree,
        module,
        logical_source,
        py_path=None,
        raw_disk_source=None,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        legacy_persisted=persisted_node_ids,
        write_sidecar=False,
    )
    tree.disk_source_sha256_hex = None
    tree.disk_source_length = 0
    # modify_tree updates module_source_sha256_hex; rollback must not leave a stale
    # digest that no longer matches tree.module.code (e.g. cst_modify_tree preview).
    tree.module_source_sha256_hex = None
    return True


CST_TREE_TTL_SECONDS: float = 900.0  # 15 minutes


async def _cst_tree_ttl_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [
            tid
            for tid, t in list(_trees.items())
            if (now - t.last_accessed_at) > CST_TREE_TTL_SECONDS
        ]
        for tid in expired:
            _trees.pop(tid, None)


def start_cst_tree_ttl_cleanup() -> None:
    asyncio.ensure_future(_cst_tree_ttl_cleanup_loop())
```

## G-001/T-003/A-003

**Target:** `code_analysis/tree/handler_registry.py`  
**Baseline line count:** 53  
**Chain:** post G-001/T-003/A-002 create (A-003 prompt embed; file not on disk yet). A-002 spec adds module docstring; A-003 embed omits it.

```python
from __future__ import annotations

from pathlib import Path
from typing import Dict

from code_analysis.tree.format_handler import FormatHandler


class HandlerNotFoundError(KeyError):
    """Raised when no FormatHandler is registered for a file extension."""

    def __init__(self, extension: str) -> None:
        super().__init__(
            f"No FormatHandler registered for extension {extension!r}"
        )
        self.extension = extension


class HandlerRegistry:
    """Central registry resolving a file to its FormatHandler by extension (C-008).

    Sole resolution path from a source file path to its FormatHandler.
    No caller may bypass the registry to select a handler directly.
    """

    def __init__(self) -> None:
        """Initialise with an empty handler map."""
        self._handlers: Dict[str, FormatHandler] = {}

    def register(self, extension: str, handler: FormatHandler) -> None:
        """Register a FormatHandler for a file extension."""
        if not extension.startswith("."):
            raise ValueError(
                f"Extension must start with a dot; got {extension!r}"
            )
        self._handlers[extension] = handler

    def resolve(self, file_path: Path) -> FormatHandler:
        """Return the FormatHandler registered for the file's extension."""
        ext = file_path.suffix
        if ext not in self._handlers:
            raise HandlerNotFoundError(ext)
        return self._handlers[ext]

    def extensions(self) -> list[str]:
        """Return sorted list of registered file extensions."""
        return sorted(self._handlers.keys())

    def __contains__(self, extension: str) -> bool:
        """Return True if a handler is registered for the extension."""
        return extension in self._handlers
```