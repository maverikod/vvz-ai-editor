"""
universal_file_preview — package for the universal_file_preview MCP command.

Exposes UniversalFilePreviewCommand as the single public entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

# Deferred import in __getattr__ avoids circular import:
# universal_file_preview_command imports submodules of this package; a top-level
# import would load this __init__ before the command module finishes loading.

__all__ = ["UniversalFilePreviewCommand"]


def __getattr__(name: str) -> Any:
    if name == "UniversalFilePreviewCommand":
        from ..universal_file_preview_command import UniversalFilePreviewCommand

        return UniversalFilePreviewCommand
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
