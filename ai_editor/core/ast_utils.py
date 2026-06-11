"""
AST utilities for parsing with comment preservation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tokenize
import io
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def parse_with_comments(source: str, filename: str = "<unknown>") -> ast.Module:
    """
    Parse Python code and preserve comments as string expressions in AST.

    Comments are added as ast.Expr(ast.Constant(value="# comment")) nodes
    before the statements they precede.

    This function extracts comments from source code using tokenize and
    inserts them into the AST as expression nodes, preserving their
    position relative to code statements.

    Args:
        source: Python source code string
        filename: Filename for error messages (used in ast.parse)

    Returns:
        AST module with comments preserved as string expressions

    Example:
        ```python
        source = '''
        # This is a comment
        def my_function():
            pass
        '''
        tree = parse_with_comments(source, "example.py")
        # tree.body[0] will be an ast.Expr with comment text
        # tree.body[1] will be the function definition
        ```
    """
    # First, parse normally
    tree = ast.parse(source, filename=filename)

    # Extract comments using tokenize
    comments_map: Dict[int, List[Tuple[int, str]]] = (
        {}
    )  # line_number -> [(col, comment)]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        for token in tokens:
            if token.type == tokenize.COMMENT:
                line_num = token.start[0]
                col = token.start[1]
                comment_text = token.string.strip()
                if line_num not in comments_map:
                    comments_map[line_num] = []
                comments_map[line_num].append((col, comment_text))
    except Exception as e:
        logger.warning(f"Failed to extract comments from {filename}: {e}")
        return tree

    # Add comments to AST as string expressions
    def add_comments_to_node(node: ast.AST, parent_body: List[ast.stmt]) -> None:
        """Recursively add comments to AST nodes."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Add comments before this node
            node_line = node.lineno
            if node_line in comments_map:
                # Find position in parent body
                try:
                    node_idx = parent_body.index(node)
                except ValueError:
                    return

                # Add comments before this node
                for col, comment_text in sorted(comments_map[node_line], reverse=True):
                    # Only add if comment is before the node definition
                    if col < node.col_offset:
                        comment_node = ast.Expr(ast.Constant(value=comment_text))
                        comment_node.lineno = node_line
                        comment_node.col_offset = col
                        parent_body.insert(node_idx, comment_node)

                # Remove from map to avoid duplicates
                del comments_map[node_line]

            # Process body recursively
            if hasattr(node, "body") and isinstance(node.body, list):
                for i, child in enumerate(node.body[:]):
                    add_comments_to_node(child, node.body)

        elif isinstance(node, ast.stmt):
            # Add comments before this statement
            node_line = node.lineno
            if node_line in comments_map:
                try:
                    node_idx = parent_body.index(node)
                except ValueError:
                    return

                for col, comment_text in sorted(comments_map[node_line], reverse=True):
                    if col < getattr(node, "col_offset", 0):
                        comment_node = ast.Expr(ast.Constant(value=comment_text))
                        comment_node.lineno = node_line
                        comment_node.col_offset = col
                        parent_body.insert(node_idx, comment_node)

                del comments_map[node_line]

    # Process all nodes in the tree
    for node in tree.body:
        add_comments_to_node(node, tree.body)

    return tree
