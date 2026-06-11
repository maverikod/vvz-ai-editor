"""
CST Tree management infrastructure.

Provides functionality for loading, modifying, and saving CST trees with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .models import CSTTree, TreeNodeMetadata, TreeOperation, TreeOperationType
from .tree_builder import (
    load_file_to_tree,
    reload_tree_from_file,
    create_tree_from_code,
)
from .tree_modifier import modify_tree
from .tree_saver import save_tree_to_file
from .tree_metadata import get_node_metadata, get_node_children, get_node_parent
from .skeleton import build_declarative_overview, skeleton_from_tree

__all__ = [
    "CSTTree",
    "TreeNodeMetadata",
    "TreeOperation",
    "TreeOperationType",
    "load_file_to_tree",
    "reload_tree_from_file",
    "create_tree_from_code",
    "modify_tree",
    "save_tree_to_file",
    "get_node_metadata",
    "get_node_children",
    "get_node_parent",
    "build_declarative_overview",
    "skeleton_from_tree",
]
