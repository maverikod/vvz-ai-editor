"""
Linear undo/redo timeline for EditSession (classic editor semantics).

Undo/redo navigate the timeline without new commits. A mutation after undo
truncates the redo branch before recording the new commit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionHistory:
    """Commit-hash timeline with a cursor (index into ``timeline``)."""

    timeline: list[str] = field(default_factory=list)
    cursor: int = 0

    def reset(self, initial_commit: str) -> None:
        """Start a fresh timeline at ``initial_commit``."""
        self.timeline = [initial_commit]
        self.cursor = 0

    def record(self, commit_hash: str) -> None:
        """Append ``commit_hash``; drop redo branch when not at tip."""
        if self.cursor < len(self.timeline) - 1:
            self.timeline = self.timeline[: self.cursor + 1]
        self.timeline.append(commit_hash)
        self.cursor = len(self.timeline) - 1

    def can_undo(self) -> bool:
        """Return True when at least one undo step exists."""
        return self.cursor > 0

    def can_redo(self) -> bool:
        """Return True when at least one redo step exists."""
        return self.cursor < len(self.timeline) - 1

    def undo_index(self) -> int:
        """Return timeline index to restore on undo."""
        if not self.can_undo():
            raise RuntimeError("nothing to undo")
        return self.cursor - 1

    def redo_index(self) -> int:
        """Return timeline index to restore on redo."""
        if not self.can_redo():
            raise RuntimeError("nothing to redo")
        return self.cursor + 1

    def move_to(self, index: int) -> None:
        """Set cursor after a successful checkout."""
        if index < 0 or index >= len(self.timeline):
            raise IndexError(f"history index out of range: {index}")
        self.cursor = index

    def current_commit(self) -> str:
        """Return commit hash at the cursor."""
        return self.timeline[self.cursor]

    def snapshot(self) -> dict[str, object]:
        """Return undo/redo availability for MCP responses."""
        return {
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "cursor": self.cursor,
            "timeline_length": len(self.timeline),
            "current_commit": self.current_commit(),
        }
