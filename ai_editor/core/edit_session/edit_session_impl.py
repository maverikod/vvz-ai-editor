"""EditSession entity: on-disk session directory and dual-mode edit lifecycle (C-019).

Distinct from ``commands.universal_file_edit.session`` (in-memory draft registry).
Supports FINAL-2 open, valid/invalid tree mutations, re-validation, and staged
external copy-out.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import enum
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, cast

from ai_editor.core.edit_session.marker_cycle import (
    denude_marked_tree,
    restore_marked_tree,
)
from ai_editor.core.edit_session.session_history import SessionHistory
from ai_editor.core.edit_session.session_repo import SessionRepo
from ai_editor.core.search_session.tree_representation import sidecar_path_for
from ai_editor.core.tree_lifecycle import (
    compute_content_checksum,
    is_tree_valid,
    validate_or_recreate_tree_file,
)
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.edit_operations import EditOperation
from ai_editor.tree.handler_registry import HandlerRegistry
from ai_editor.tree.sibling_convention import sibling_tree_path


class SessionTreeValidity(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"


class EditSessionError(ValueError):
    """EditSession lifecycle violations."""


CONTENT_NOT_ALLOWED_FOR_VALID_FILE = "CONTENT_NOT_ALLOWED_FOR_VALID_FILE"

SESSION_VALID_TRUTH_INVARIANT = (
    "When tree_validity is valid, the in-session tree is truth; "
    "the external SourceFile is stale."
)
SESSION_INVALID_TRUTH_INVARIANT = (
    "When tree_validity is invalid, the in-session source copy is the editing surface."
)

#: Process-level registry; open registers, close removes (C-019).
_active_sessions: dict[str, EditSession] = {}


def _external_source_and_tree_valid(
    *,
    source_abs: Path,
    project_root: Path,
    file_path: str,
) -> bool:
    """Return True when external source parses and tree checksums align (FINAL-2)."""
    if not source_abs.is_file():
        return False
    external_text = source_abs.read_text(encoding="utf-8")
    try:
        HandlerRegistry.default_registry().resolve(source_abs).parse_content(
            Path(file_path),
            external_text,
        )
    except Exception:
        return False
    try:
        ref, _validity_state = validate_or_recreate_tree_file(
            project_root=project_root,
            file_path=file_path,
        )
    except Exception:
        return False
    ext_checksum = compute_content_checksum(external_text)
    return is_tree_valid(ext_checksum, ref.content_checksum)


def _session_sidecar_in_edit_subdir(
    session_dir: Path,
    session_source_path: Path,
) -> Path:
    """Return CST sidecar path inside Edit Subdirectory (C-008)."""
    resolved_dir = session_dir.resolve()
    resolved_source = session_source_path.resolve()
    try:
        resolved_source.relative_to(resolved_dir)
    except ValueError as exc:
        raise EditSessionError(
            "WORKSPACE_PATH_ESCAPE",
            "session_source_path must be inside session_dir (edit subdir)",
        ) from exc
    return cast(Path, sibling_tree_path(resolved_source))


@dataclass
class EditSession:
    """On-disk edit session with dual-mode valid/invalid tree lifecycle (C-019)."""

    session_id: str
    source_abs: Path
    tree_abs: Path
    session_dir: Path
    session_source_path: Path
    session_tree_path: Path
    session_repo_path: Path
    session_repo: SessionRepo
    project_root: Path
    file_path: str
    tree_validity: SessionTreeValidity
    source_checksum: str
    tree_checksum: Optional[str]
    is_open: bool = field(default=False)
    history: SessionHistory = field(default_factory=SessionHistory)
    workspace_session_root: Optional[Path] = None
    workspace_file_subtree_root: Optional[Path] = None

    @classmethod
    def open(
        cls,
        *,
        source_abs: Path,
        project_root: Path,
        file_path: str,
        content: Optional[str] = None,
        workspace_session_root: Optional[Path] = None,
        workspace_file_subtree_root: Optional[Path] = None,
        workspace_origin_path: Optional[Path] = None,
        workspace_edit_subdir: Optional[Path] = None,
    ) -> EditSession:
        if content is not None and source_abs.is_file():
            if _external_source_and_tree_valid(
                source_abs=source_abs,
                project_root=project_root,
                file_path=file_path,
            ):
                raise EditSessionError(
                    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,
                    "content parameter not allowed when source and tree are valid",
                )

        _ws = (
            workspace_session_root,
            workspace_file_subtree_root,
            workspace_origin_path,
            workspace_edit_subdir,
        )
        workspace_mode = all(p is not None for p in _ws)
        if any(p is not None for p in _ws) and not workspace_mode:
            raise EditSessionError(
                "WORKSPACE_PATHS_INCOMPLETE",
                "all four workspace_* paths required together",
            )

        session_id = str(uuid.uuid4())

        if workspace_mode:
            assert workspace_session_root is not None
            assert workspace_file_subtree_root is not None
            assert workspace_origin_path is not None
            assert workspace_edit_subdir is not None
            ws_session = workspace_session_root.resolve()
            ws_subtree = workspace_file_subtree_root.resolve()
            ws_origin = workspace_origin_path.resolve()
            session_dir = workspace_edit_subdir.resolve()

            try:
                ws_subtree.relative_to(ws_session)
            except ValueError as exc:
                raise EditSessionError(
                    "WORKSPACE_PATH_ESCAPE",
                    "file subtree must be under session directory",
                ) from exc
            try:
                ws_origin.relative_to(ws_subtree)
            except ValueError as exc:
                raise EditSessionError(
                    "WORKSPACE_PATH_ESCAPE",
                    "origin path must be under file subtree",
                ) from exc
            try:
                session_dir.relative_to(ws_subtree)
            except ValueError as exc:
                raise EditSessionError(
                    "WORKSPACE_PATH_ESCAPE",
                    "edit subdir must be under file subtree",
                ) from exc

            session_dir.mkdir(parents=True, exist_ok=True)
            session_source_path = session_dir / ws_origin.name
            if content is not None:
                session_source_path.write_text(content, encoding="utf-8")
            elif ws_origin.is_file():
                shutil.copy2(ws_origin, session_source_path)
            elif source_abs.is_file():
                shutil.copy2(source_abs, session_source_path)
            else:
                raise EditSessionError("SOURCE_MISSING")

            source_text = session_source_path.read_text(encoding="utf-8")
            source_checksum = compute_content_checksum(source_text)

            session_tree_path = _session_sidecar_in_edit_subdir(
                session_dir, session_source_path
            )
            tree_abs = session_tree_path

            if session_source_path.suffix == ".py" and not session_tree_path.is_file():
                try:
                    from ai_editor.core.cst_tree import tree_builder as cst_builder

                    cst_builder.load_file_to_tree(str(session_source_path))
                except Exception:
                    pass

            tree_validity = SessionTreeValidity.INVALID
            tree_checksum: Optional[str] = None
            if session_tree_path.is_file():
                tree_text = session_tree_path.read_text(encoding="utf-8")
                tree_checksum = compute_content_checksum(tree_text)
                try:
                    HandlerRegistry.default_registry().resolve(ws_origin).parse_content(
                        Path(file_path),
                        source_text,
                    )
                    sections = parse_tree_file(tree_text)
                    if sections.checksums.get("source_sha256") == source_checksum:
                        tree_validity = SessionTreeValidity.VALID
                except Exception:
                    tree_validity = SessionTreeValidity.INVALID

            include_tree = (
                tree_validity == SessionTreeValidity.VALID
                and session_tree_path.is_file()
            )

            session_repo_path = session_dir
            session_repo = SessionRepo.init(
                repo_dir=session_dir,
                source_name=session_source_path.name,
                tree_name=session_tree_path.name,
                include_tree=include_tree,
                source_abs=ws_origin,
            )
            history = SessionHistory()
            history.reset(session_repo.log()[-1].hash)

            session = cls(
                session_id=session_id,
                source_abs=ws_origin,
                tree_abs=tree_abs,
                session_dir=session_dir,
                session_source_path=session_source_path,
                session_tree_path=session_tree_path,
                session_repo_path=session_repo_path,
                session_repo=session_repo,
                project_root=project_root,
                file_path=file_path,
                tree_validity=tree_validity,
                source_checksum=source_checksum,
                tree_checksum=tree_checksum,
                is_open=True,
                history=history,
                workspace_session_root=ws_session,
                workspace_file_subtree_root=ws_subtree,
            )
            _active_sessions[session_id] = session
            return session

        session_dir = source_abs.parent / f"{source_abs.name}-{session_id}"
        session_dir.mkdir(exist_ok=False)

        session_source_path = session_dir / source_abs.name
        if content is not None:
            session_source_path.write_text(content, encoding="utf-8")
        elif source_abs.is_file():
            shutil.copy2(source_abs, session_source_path)
        else:
            raise EditSessionError("SOURCE_MISSING")

        source_text = session_source_path.read_text(encoding="utf-8")
        source_checksum = compute_content_checksum(source_text)

        resolved_root = project_root.resolve()
        tree_abs = sidecar_path_for(file_path, resolved_root)
        ref_content_checksum: Optional[str] = None
        try:
            ref, _validity_state = validate_or_recreate_tree_file(
                project_root=project_root,
                file_path=file_path,
            )
            tree_abs = ref.sidecar_path
            ref_content_checksum = ref.content_checksum
        except Exception:
            ref_content_checksum = None

        session_tree_path = session_dir / tree_abs.name
        if tree_abs.is_file():
            shutil.copy2(tree_abs, session_tree_path)

        try:
            HandlerRegistry.default_registry().resolve(source_abs).parse_content(
                Path(file_path),
                source_text,
            )
            if (
                session_tree_path.is_file()
                and ref_content_checksum is not None
                and is_tree_valid(source_checksum, ref_content_checksum)
            ):
                tree_validity = SessionTreeValidity.VALID
            else:
                tree_validity = SessionTreeValidity.INVALID
        except Exception:
            tree_validity = SessionTreeValidity.INVALID

        session_repo_path = session_dir
        tree_checksum = (
            compute_content_checksum(session_tree_path.read_text(encoding="utf-8"))
            if session_tree_path.is_file()
            else None
        )

        include_tree = (
            tree_validity == SessionTreeValidity.VALID and session_tree_path.is_file()
        )
        session_repo = SessionRepo.init(
            repo_dir=session_dir,
            source_name=session_source_path.name,
            tree_name=session_tree_path.name,
            include_tree=include_tree,
            source_abs=source_abs,
        )
        history = SessionHistory()
        history.reset(session_repo.log()[-1].hash)

        session = cls(
            session_id=session_id,
            source_abs=source_abs,
            tree_abs=tree_abs,
            session_dir=session_dir,
            session_source_path=session_source_path,
            session_tree_path=session_tree_path,
            session_repo_path=session_repo_path,
            session_repo=session_repo,
            project_root=project_root,
            file_path=file_path,
            tree_validity=tree_validity,
            source_checksum=source_checksum,
            tree_checksum=tree_checksum,
            is_open=True,
            history=history,
        )
        _active_sessions[session_id] = session
        return session

    def apply_tree_operation(self, operation: EditOperation) -> None:
        """Apply one G-004 EditOperation on the in-session marked tree ({h008})."""
        from ai_editor.core.edit_session.edit_operations_adapter import (
            apply_edit_on_session_tree,
        )

        apply_edit_on_session_tree(self, operation)

    def apply_valid_tree_mutation(
        self,
        mutation_fn: Callable[[str], str],
    ) -> None:
        if not self.is_open or self.tree_validity != SessionTreeValidity.VALID:
            raise RuntimeError(
                "Valid-tree mutation requires open session with valid tree"
            )
        marked = self.session_tree_path.read_text(encoding="utf-8")
        denuded, state = denude_marked_tree(
            source_abs=self.source_abs,
            marked_tree=marked,
        )
        denuded_after = mutation_fn(denuded)
        restored = restore_marked_tree(
            source_abs=self.source_abs,
            denuded_after_mutation=denuded_after,
            state=state,
        )
        self.session_tree_path.write_text(restored, encoding="utf-8")
        self._post_mutation_full()

    def apply_plaintext_mutation(self, new_source_text: str) -> None:
        if not self.is_open or self.tree_validity != SessionTreeValidity.INVALID:
            raise RuntimeError(
                "Plaintext mutation requires open session with invalid tree"
            )
        self.session_source_path.write_text(new_source_text, encoding="utf-8")
        self.source_checksum = compute_content_checksum(new_source_text)
        self._post_mutation_degraded()
        _mut.try_revalidate(self)

    def apply_cst_sidecar_mutation(
        self,
        new_source_text: str,
        *,
        sidecar_abs: Path,
    ) -> None:
        """Sync session workspace after legacy CST ``write_sidecar_atomic`` edit."""
        if not self.is_open:
            raise RuntimeError("EditSession is not open")
        if self.workspace_session_root is not None:
            resolved_sidecar = sidecar_abs.resolve()
            resolved_dir = self.session_dir.resolve()
            try:
                resolved_sidecar.relative_to(resolved_dir)
            except ValueError as exc:
                raise EditSessionError(
                    "WORKSPACE_SIDECAR_ESCAPE",
                    f"sidecar must be under edit subdir {resolved_dir}, "
                    f"got {resolved_sidecar}",
                ) from exc
        self.session_source_path.write_text(new_source_text, encoding="utf-8")
        if sidecar_abs.resolve() != self.session_tree_path.resolve():
            shutil.copy2(sidecar_abs, self.session_tree_path)
        self.source_checksum = compute_content_checksum(new_source_text)
        self.tree_checksum = compute_content_checksum(
            self.session_tree_path.read_text(encoding="utf-8")
        )
        self.tree_validity = SessionTreeValidity.VALID
        self.session_repo.commit_full(message="session: mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _post_mutation_full(self) -> None:
        _mut.export_source_via_unmark(self)
        self.source_checksum = compute_content_checksum(
            self.session_source_path.read_text(encoding="utf-8")
        )
        _mut.update_session_tree_checksums(self, self.source_checksum)
        self.tree_checksum = compute_content_checksum(
            self.session_tree_path.read_text(encoding="utf-8")
        )
        self.session_repo.commit_full(message="session: mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _post_mutation_degraded(self) -> None:
        self.source_checksum = compute_content_checksum(
            self.session_source_path.read_text(encoding="utf-8")
        )
        self.tree_checksum = None
        self.session_repo.commit_degraded(message="session: plaintext mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _record_history_commit(self, commit_hash: str) -> None:
        self.history.record(commit_hash)

    def _sync_state_after_checkout(self, *, mode: str) -> None:
        source_text = self.session_source_path.read_text(encoding="utf-8")
        self.source_checksum = compute_content_checksum(source_text)
        if mode == "full":
            self.tree_validity = SessionTreeValidity.VALID
            self.tree_checksum = (
                compute_content_checksum(
                    self.session_tree_path.read_text(encoding="utf-8")
                )
                if self.session_tree_path.is_file()
                else None
            )
            return
        self.tree_validity = SessionTreeValidity.INVALID
        self.tree_checksum = None

    def checkout_history_index(self, index: int) -> None:
        """Restore working artefacts to ``timeline[index]`` without a new commit."""
        _mut.checkout_history_index(self, index)

    def undo(self) -> dict[str, object]:
        """Step back one edit; classic undo without creating a commit."""
        return _mut.undo(self)

    def redo(self) -> dict[str, object]:
        """Step forward one edit; classic redo without creating a commit."""
        return _mut.redo(self)

    def record_revert_commit(self, *, rev: str) -> str:
        """Git-style revert: checkout ``rev`` and append a new tracked commit."""
        return _mut.record_revert_commit(self, rev=rev)

    def preview_external_write(self) -> dict[str, Any]:
        """Compute unified diffs of in-session artefacts vs live external files; no external writes."""
        return _mut.preview_external_write(self)

    def confirm_external_copy_out(self) -> None:
        """Atomically copy in-session artefacts to external co-located paths; both or neither when valid."""
        _mut.confirm_external_copy_out(self)

    def close(self) -> None:
        _mut.close(self)

    def record_tree_modification(self) -> None:
        _mut.record_tree_modification(self)


def get_active_session(session_id: str) -> EditSession:
    """Resolve live EditSession; KeyError if absent (no sessionless access)."""
    try:
        return _active_sessions[session_id]
    except KeyError as exc:
        raise KeyError(f"No active edit session: {session_id}") from exc


from . import edit_session_mutations as _mut  # noqa: E402
