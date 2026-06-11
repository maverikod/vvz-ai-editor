"""
Python preview registration stub — navigation uses marked-tree only.

Legacy ``PythonFileHandler`` (CST UUID / ``load_file_to_tree``) was removed.
``HandlerDispatcher`` still maps ``.py`` extensions to this placeholder.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import INPUT_ERROR_CONFLICTING_PARAMETERS, PreviewError, input_error
from ..models import Node


class PythonMarkedTreeHandler(FileHandler):
    """Placeholder handler: Python preview is marked-tree navigation only."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".py", ".pyi", ".pyw"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "Python preview uses marked-tree navigation only; provide project_id.",
            details={"file_path": file_path},
        )

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "Python preview uses marked-tree navigation only; node_ref must be short_id.",
            details={"node_ref": node_ref},
        )
