"""Round-trip serializer for the tree-temp INI model."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

from ai_editor.core.tree_temp.ini_source_parser import ConfigContainer, ConfigKey
from ai_editor.core.tree_temp.tree_node import TreeNode


def _emit_trivia(trivia: Optional[str]) -> str:
    if not trivia:
        return ""
    return trivia if trivia.endswith("\n") else trivia + "\n"


def _split_inline_comment(value: str) -> tuple[str, str]:
    for index, char in enumerate(value):
        if char in "#;" and index > 0 and value[index - 1].isspace():
            return value[:index], value[index:]
    return value, ""


def _key_style(node: ConfigKey) -> tuple[str, str, str, str]:
    """Return left-side, separator, value-leading, and value-trailing style."""
    match = re.match(r"^(.*?)(=|:)(.*)$", node.raw_line)
    if match is None:
        return node.key_prefix, node.separator, " ", ""
    left, separator, raw_value = match.groups()
    body, _comment = _split_inline_comment(raw_value)
    leading = body[: len(body) - len(body.lstrip())]
    trailing = body[len(body.rstrip()) :]
    return left, separator, leading, trailing


def _find_style(children: Sequence[TreeNode]) -> tuple[str, str, str, str]:
    for child in children:
        if isinstance(child, ConfigKey):
            return _key_style(child)
    return "", "=", " ", ""


def _key_comment(node: TreeNode) -> str:
    if node.comment_inline:
        return node.comment_inline
    if isinstance(node, ConfigKey):
        return node.value_suffix
    return ""


def _emit_key(node: TreeNode, style: tuple[str, str, str, str]) -> str:
    if not isinstance(node.key, str) or not node.key:
        raise ValueError("INI key node requires a non-empty string key")
    if node.type != "string" or not isinstance(node.value, str):
        raise ValueError("INI key node requires a string value")

    left, separator, leading, trailing = style
    if isinstance(node, ConfigKey):
        left, separator, leading, trailing = _key_style(node)
        if left.strip() != node.key:
            left = f"{node.key_prefix}{node.key}"
    elif left:
        prefix = left[: len(left) - len(left.lstrip())]
        suffix = left[len(left.rstrip()) :]
        left = f"{prefix}{node.key}{suffix}"
    else:
        left = node.key
    body = f"{left}{separator}{leading}{node.value}{trailing}"
    comment = _key_comment(node)
    if comment:
        body += comment if comment.startswith(("#", ";")) else " " + comment
    return body


def _emit_container(container: ConfigContainer) -> str:
    children = list(container.children or [])
    style = _find_style(children)
    out: List[str] = []
    for child in children:
        if isinstance(child, ConfigContainer):
            out.append(_emit_trivia(child.leading_trivia))
            out.append(child.raw_header)
            out.append("\n")
            out.append(_emit_container(child))
        else:
            out.append(_emit_trivia(child.comment_before))
            out.append(_emit_key(child, style))
            out.append("\n")
    out.append(_emit_trivia(container.trailing_trivia))
    return "".join(out)


def serialize_ini_source(root_nodes: Iterable[TreeNode]) -> str:
    """Serialize one INI ``ConfigContainer`` root.

    Child-list order is authoritative, so before/after/first/last inserts are
    emitted in the position selected by the mutation operation.
    """
    roots = list(root_nodes)
    if not roots:
        return ""
    if len(roots) != 1 or not isinstance(roots[0], ConfigContainer):
        raise ValueError("INI serialization requires one ConfigContainer root")
    return _emit_container(roots[0])


emit_ini_source_from_roots = serialize_ini_source

__all__ = ["emit_ini_source_from_roots", "serialize_ini_source"]
