"""JSON SourceParser entry alias for tree-temp (G-005 import compatibility).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.json_source_parser import parse_json_source

parse_json_source_to_roots = parse_json_source

__all__ = ["parse_json_source_to_roots"]
