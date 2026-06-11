"""YAML SourceParser entry alias for tree-temp (G-005 import compatibility).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.tree_temp.yaml_source_parser import parse_yaml_source

parse_yaml_source_to_roots = parse_yaml_source

__all__ = ["parse_yaml_source_to_roots"]
