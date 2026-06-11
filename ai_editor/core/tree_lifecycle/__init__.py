"""
Tree-lifecycle package: centralized checksum + validate + recreate of trees.

See ``checksum`` for the content-core and the file wrapper.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.core.tree_lifecycle.lifecycle import TreeLifecycle
from ai_editor.core.tree_lifecycle.checksum import (
    ChecksumSyncPolicy,
    ShaSyncBranch,
    ShaSyncDecision,
    compute_content_checksum,
    is_tree_valid,
    recreate_tree_from_content,
    validate_or_recreate_from_content,
    validate_or_recreate_tree_file,
)

__all__ = [
    "ChecksumSyncPolicy",
    "ShaSyncBranch",
    "ShaSyncDecision",
    "TreeBuilder",
    "TreeLifecycle",
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
