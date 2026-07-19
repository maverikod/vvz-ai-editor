"""Round-trip serializer for the tree-temp TOML model."""

from __future__ import annotations

import json
import re
from typing import Iterable, List, Sequence, Tuple

from ai_editor.core.tree_temp.toml_source_parser import (
    TomlConfigContainer,
    TomlConfigKey,
    _decode_value,
)
from ai_editor.core.tree_temp.tree_node import TreeNode


def _emit_trivia(trivia: str | None) -> str:
    if not trivia:
        return ""
    return trivia if trivia.endswith("\n") else trivia + "\n"


def _key_style(node: TomlConfigKey) -> Tuple[str, str, str, str]:
    """Return left side, separator, value-leading, and value-trailing style."""
    match = re.match(r"^(.*?)(=)(.*)$", node.raw_line)
    if match is None:
        return node.key_prefix, node.separator, " ", ""
    left, separator, raw_value = match.groups()
    body = raw_value
    if node.value_suffix and body.rstrip().endswith(node.value_suffix):
        body = body.rstrip()[: -len(node.value_suffix)]
    return (
        left,
        separator,
        body[: len(body) - len(body.lstrip())],
        body[len(body.rstrip()) :],
    )


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        raise ValueError("TOML does not support null values")
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{key} = {_toml_value(item)}" for key, item in value.items()
        ) + " }"
    raise ValueError(f"Unsupported TOML value type: {type(value).__name__}")


def _node_value(node: TreeNode) -> object:
    if node.type == "array":
        return [_node_value(child) for child in node.children or []]
    if node.type == "object":
        return {
            child.key: _node_value(child)
            for child in node.children or []
            if child.key is not None
        }
    return node.value


def _value_text(node: TreeNode) -> str:
    if isinstance(node, TomlConfigKey) and node.value_raw:
        try:
            if _decode_value(node.value_raw) == _node_value(node):
                return node.value_raw
        except ValueError:
            pass
    return _toml_value(_node_value(node))


def _emit_key(node: TreeNode, style: Tuple[str, str, str, str]) -> str:
    if not isinstance(node.key, str) or not node.key:
        raise ValueError("TOML key node requires a non-empty string key")
    if isinstance(node, TomlConfigKey):
        left, separator, leading, trailing = _key_style(node)
        if left.strip() != node.key:
            left = f"{node.key_prefix}{node.key}"
    else:
        left, separator, leading, trailing = style
        prefix = left[: len(left) - len(left.lstrip())]
        suffix = left[len(left.rstrip()) :]
        left = f"{prefix}{node.key}{suffix}" if left else node.key
    body = f"{left}{separator}{leading}{_value_text(node)}{trailing}"
    if node.comment_inline:
        comment = node.comment_inline
        body += comment if comment.startswith("#") else " " + comment
    return body


def _find_style(children: Sequence[TreeNode]) -> Tuple[str, str, str, str]:
    for child in children:
        if isinstance(child, TomlConfigKey):
            return _key_style(child)
    return "", "=", " ", ""


def _emit_container(container: TomlConfigContainer, *, include_header: bool = False) -> str:
    children = list(container.children or [])
    style = _find_style(children)
    out: List[str] = []
    if include_header:
        out.append(_emit_trivia(container.leading_trivia))
        header = container.raw_header
        if not header:
            marker = "[[" if container.is_array_table else "["
            header = marker + (container.table_name or ".".join(container.dotted_path))
            header += "]]" if container.is_array_table else "]"
            if container.comment_inline:
                header += " " + container.comment_inline
        out.extend((header, "\n"))
    for child in children:
        if isinstance(child, TomlConfigContainer):
            out.append(_emit_container(child, include_header=True))
        else:
            out.append(_emit_trivia(child.comment_before))
            out.extend((_emit_key(child, style), getattr(child, "line_ending", "\n") or "\n"))
    out.append(_emit_trivia(container.trailing_trivia))
    return "".join(out)


def serialize_toml_source(root_nodes: Iterable[TreeNode]) -> str:
    """Serialize one ``TomlConfigContainer`` root using child-list order."""
    roots = list(root_nodes)
    if not roots:
        return ""
    if len(roots) != 1 or not isinstance(roots[0], TomlConfigContainer):
        raise ValueError("TOML serialization requires one TomlConfigContainer root")
    return _emit_container(roots[0])


emit_toml_source_from_roots = serialize_toml_source

__all__ = ["emit_toml_source_from_roots", "serialize_toml_source"]
