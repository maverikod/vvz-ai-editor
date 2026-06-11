"""
Session git repository for EditSession per-mutation history (C-013).

Ephemeral dulwich-backed repo inside the session directory; one commit per
mutation with FULL (tree+source) or DEGRADED (source-only) shape.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, cast

from dulwich import porcelain as porcelain
from ai_editor.core.tree_lifecycle.node_id_map import (
    SECTION_CHECKSUMS_START,
    parse_tree_file,
)
from ai_editor.tree.handler_registry import HandlerRegistry
from dulwich.object_store import tree_lookup_path
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

ONE_COMMIT_PER_MUTATION_INVARIANT: str = (
    "Every mutation produces exactly one SessionRepo commit; "
    "FULL captures tree+source; DEGRADED captures source only."
)

SESSION_COMMIT_IDENTITY: bytes = b"AI Editor EditSession <edit@local>"


@dataclass(frozen=True)
class SessionCommit:
    hash: str
    message: str
    timestamp: int


class SessionRepo:
    """Ephemeral session-scoped git repository (C-013)."""

    def __init__(
        self,
        *,
        repo_dir: Path,
        source_name: str,
        tree_name: str,
        source_abs: Path,
        repo: Repo,
    ) -> None:
        self._repo_dir = repo_dir
        self._source_name = source_name
        self._tree_name = tree_name
        self._source_abs = source_abs
        self._repo = repo

    @classmethod
    def init(
        cls,
        *,
        repo_dir: Path,
        source_name: str,
        tree_name: str,
        include_tree: bool,
        source_abs: Path,
    ) -> SessionRepo:
        """Init repo; initial commit FULL if include_tree else DEGRADED."""
        repo = Repo.init(str(repo_dir))
        instance = cls(
            repo_dir=repo_dir,
            source_name=source_name,
            tree_name=tree_name,
            source_abs=source_abs,
            repo=repo,
        )
        if include_tree:
            instance.commit_full(message="session: initial commit")
        else:
            instance.commit_degraded(message="session: initial commit (degraded)")
        return instance

    def commit_full(self, *, message: str) -> str:
        """Stage source_name + tree_name; one commit (valid-tree {d003})."""
        paths = [
            str(self._repo_dir / self._source_name),
            str(self._repo_dir / self._tree_name),
        ]
        porcelain.add(self._repo, paths=paths)
        sha = porcelain.commit(
            self._repo,
            message=message.encode("utf-8"),
            author=SESSION_COMMIT_IDENTITY,
            committer=SESSION_COMMIT_IDENTITY,
        )
        return sha.decode("ascii")

    def commit_degraded(self, *, message: str) -> str:
        """Stage source_name only (invalid-tree DEGRADED {d003})."""
        paths = [str(self._repo_dir / self._source_name)]
        porcelain.add(self._repo, paths=paths)
        sha = porcelain.commit(
            self._repo,
            message=message.encode("utf-8"),
            author=SESSION_COMMIT_IDENTITY,
            committer=SESSION_COMMIT_IDENTITY,
        )
        return sha.decode("ascii")

    def log(self) -> List[SessionCommit]:
        commits: List[SessionCommit] = []
        for entry in self._repo.get_walker():
            commit = entry.commit
            commits.append(
                SessionCommit(
                    hash=commit.id.decode("ascii"),
                    message=commit.message.decode("utf-8"),
                    timestamp=commit.commit_time,
                )
            )
        return commits

    def show_tree(self, *, rev: str) -> bytes:
        return self._blob_bytes_at_commit(rev=rev, name=self._tree_name)

    def show_source(self, *, rev: str) -> bytes:
        return self._blob_bytes_at_commit(rev=rev, name=self._source_name)

    def status_is_clean(self) -> bool:
        """Compare working tree to HEAD for tracked files present in latest commit."""
        try:
            head = self._repo.head()
        except KeyError:
            return False
        commit = cast(Commit, self._repo[head])
        tree = cast(Tree, self._repo[commit.tree])
        for entry in tree.items():
            rel_path = entry.path.decode("utf-8")
            working_path = self._repo_dir / rel_path
            if not working_path.is_file():
                return False
            blob = cast(Blob, self._repo.get_object(entry.sha))
            if working_path.read_bytes() != blob.data:
                return False
        return True

    def revision_includes_tree(self, *, rev: str) -> bool:
        """Return True when ``rev`` tracks the marked tree blob."""
        commit = cast(Commit, self._repo[rev.encode("ascii")])
        tree = cast(Tree, self._repo[commit.tree])
        for entry in tree.items():
            if entry.path.decode("utf-8") == self._tree_name:
                return True
        return False

    def _try_blob_bytes_at_commit(self, *, rev: str, name: str) -> bytes | None:
        try:
            return self._blob_bytes_at_commit(rev=rev, name=name)
        except KeyError:
            return None

    def checkout_revision(self, *, rev: str) -> str:
        """Restore working files to ``rev`` without creating a commit.

        Returns:
            ``"full"`` when source and tree were restored; ``"degraded"`` when
            only source was restored (invalid-tree history entry).
        """
        source_path = self._repo_dir / self._source_name
        tree_path = self._repo_dir / self._tree_name
        tree_bytes = self._try_blob_bytes_at_commit(rev=rev, name=self._tree_name)
        if tree_bytes is not None:
            tree_path.write_bytes(tree_bytes)
            tree_text = tree_bytes.decode("utf-8")
            if SECTION_CHECKSUMS_START in tree_text:
                self._sync_source_from_tree()
            else:
                source_blob = self._try_blob_bytes_at_commit(
                    rev=rev, name=self._source_name
                )
                if source_blob is not None:
                    source_path.write_bytes(source_blob)
            return "full"
        source_blob = self._blob_bytes_at_commit(rev=rev, name=self._source_name)
        source_path.write_bytes(source_blob)
        if tree_path.is_file():
            tree_path.unlink()
        return "degraded"

    def revert(self, *, rev: str) -> str:
        """Restore tree file at rev; unmark-export source; commit_full revert message."""
        self.checkout_revision(rev=rev)
        return self.commit_full(message=f"session: revert to {rev}")

    def _sync_source_from_tree(self) -> None:
        """Unmark-export TREE section to session source file."""
        tree_path = self._repo_dir / self._tree_name
        source_path = self._repo_dir / self._source_name
        tree_text = tree_path.read_text(encoding="utf-8")
        handler = HandlerRegistry.default_registry().resolve(self._source_abs)
        sections = parse_tree_file(tree_text)
        clean = handler.unmark(sections.tree)
        source_path.write_text(clean, encoding="utf-8")

    def _blob_bytes_at_commit(self, *, rev: str, name: str) -> bytes:
        commit = cast(Commit, self._repo[rev.encode("ascii")])
        tree = cast(Tree, self._repo[commit.tree])
        try:
            _, blob_sha = tree_lookup_path(
                self._repo.get_object,
                tree.id,
                name.encode("utf-8"),
            )
        except KeyError as exc:
            raise KeyError(name) from exc
        blob = cast(Blob, self._repo.get_object(blob_sha))
        return blob.data
