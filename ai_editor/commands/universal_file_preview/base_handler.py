"""
FileHandler ABC for universal_file_preview.

Defines the abstract interface (C-003) that every file handler must
implement. Each handler opens one family of files and produces the
uniform Node representation. StableIdentifier (C-009) format is
opaque at this level; each handler interprets it natively.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import abc
from typing import Any

from .budget import PreviewBudget
from .errors import PreviewError
from .models import Node


class FileHandler(abc.ABC):
    """
    Abstract base for file handlers (C-003).

    Each concrete handler opens one family of files (by extension) and
    produces the uniform in-memory Node representation. Navigation logic
    is not implemented here; it lives in NavigationProcedure (C-006).

    Attributes:
        supported_extensions: Frozenset of lowercase extensions this
                              handler accepts (e.g. frozenset({'.py'})).
    """

    @property
    @abc.abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase file extensions this handler supports."""

    @abc.abstractmethod
    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """
        Open the file and return the root Node.

        On success returns the root Node (NodeKind depends on handler).
        On parse failure returns a file_structure_error PreviewError.

        Args:
            file_path: Project-relative path to the file.
            session: An existing in-memory tree session (TreeSession C-011),
                     or None when no session is provided by the caller.
            budget: Optional size caps; handlers that do not use them may ignore.

        Returns:
            Root Node or PreviewError.
        """

    @abc.abstractmethod
    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a StableIdentifier (C-009) to the specific Node it addresses.

        The identifier format is native to this handler and opaque to the
        dispatcher. On failure returns an UNKNOWN_NODE_REF PreviewError.

        Args:
            node_ref: StableIdentifier string in this handler's native format.
            session: In-memory tree session, or None.

        Returns:
            Resolved Node or PreviewError.
        """

    def default_focus(
        self,
        file_path: str,
        node_ref: str | None,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve the focus Node from file_path and optional node_ref (C-010).

        When node_ref is None the focus is the file root (open_root).
        When node_ref is provided the focus is the specific node resolved
        by resolve_node_ref. On any error returns a PreviewError.

        Args:
            file_path: Project-relative path to the file.
            node_ref: StableIdentifier (C-009) or None.
            session: In-memory tree session or None.

        Returns:
            Focus Node or PreviewError.
        """
        if node_ref is None:
            return self.open_root(file_path, session)
        root_result = self.open_root(file_path, session)
        if isinstance(root_result, PreviewError):
            return root_result
        return self.resolve_node_ref(node_ref, session)
