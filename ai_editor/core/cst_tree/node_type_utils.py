"""
Helpers for deriving semantic attributes of LibCST nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional
import uuid

import libcst as cst


def get_decorator_expression(node: cst.Decorator) -> str:
    """Return ``@...`` source text for a LibCST Decorator node."""
    try:
        expr = node.decorator
        if isinstance(expr, cst.Name):
            return f"@{expr.value}"
        if isinstance(expr, cst.Attribute):
            parts: list[str] = []
            cur: cst.BaseExpression = expr
            while isinstance(cur, cst.Attribute):
                parts.append(cur.attr.value)
                cur = cur.value
            if isinstance(cur, cst.Name):
                parts.append(cur.value)
            return "@" + ".".join(reversed(parts))
        return f"@{expr}"
    except Exception:
        return "@decorator"


def decorator_stable_id(parent_qualname: Optional[str], index: int) -> str:
    """Deterministic stable_id for a decorator from parent qualname and index."""
    key = f"{parent_qualname or 'module'}:decorator:{index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def get_node_name(node: cst.CSTNode) -> Optional[str]:
    """Return the semantic name of a node when available."""
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return node.name.value
    if isinstance(node, cst.Name):
        return node.value
    return None


def get_node_kind(node: cst.CSTNode, class_stack: list[str]) -> str:
    """Return the semantic kind used by CST commands and selectors."""
    if isinstance(node, cst.Module):
        return "module"
    if isinstance(node, cst.Decorator):
        return "decorator"
    if isinstance(node, cst.ClassDef):
        return "class"
    if isinstance(node, cst.FunctionDef):
        return "method" if class_stack else "function"
    if isinstance(node, (cst.Import, cst.ImportFrom)):
        return "import"
    if isinstance(node, cst.BaseSmallStatement):
        return "smallstmt"
    if isinstance(node, cst.BaseStatement):
        return "stmt"
    return "node"


def get_node_qualname(
    node: cst.CSTNode,
    class_stack: list[str],
    func_stack: list[str],
) -> Optional[str]:
    """Return the qualified name for class/function-like nodes."""
    if isinstance(node, cst.ClassDef):
        return (
            ".".join(class_stack + [node.name.value])
            if class_stack
            else node.name.value
        )
    if isinstance(node, cst.FunctionDef):
        if class_stack:
            return ".".join(class_stack + [node.name.value])
        parts = list(func_stack[:-1]) + [node.name.value]
        return ".".join(parts) if parts else node.name.value
    return ".".join(class_stack + func_stack) if (class_stack or func_stack) else None
