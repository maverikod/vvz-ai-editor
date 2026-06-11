"""JSON SourceSerializer entry alias for tree-temp (G-005 import compatibility).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.json_source_serializer import serialize_json_source

emit_json_source_from_roots = serialize_json_source

__all__ = ["emit_json_source_from_roots"]
