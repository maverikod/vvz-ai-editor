"""YAML SourceSerializer entry alias for tree-temp (G-005 import compatibility).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.yaml_source_serializer import serialize_yaml_source

emit_yaml_source_from_roots = serialize_yaml_source

__all__ = ["emit_yaml_source_from_roots"]
