"""Round-trip oriented TOML parser for the tree-temp configuration model."""

from __future__ import annotations

import re
import tomllib
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from ai_editor.core.tree_temp.tree_node import TreeNode, TreeNodeType


@dataclass
class TomlConfigKey(TreeNode):
    """A TOML assignment with source and insertion metadata."""

    source_line: int = 0
    end_line: int = 0
    raw_line: str = ""
    key_prefix: str = ""
    separator: str = "="
    value_raw: str = ""
    value_suffix: str = ""
    line_ending: str = ""
    insert_before_line: int = 0
    insert_after_line: int = 0

    @property
    def line_start(self) -> int:
        return self.source_line

    @property
    def line_end(self) -> int:
        return self.end_line


@dataclass
class TomlConfigContainer(TreeNode):
    """The TOML document or a table header with source anchors."""

    source_line: int = 1
    end_line: int = 0
    raw_header: str = ""
    leading_trivia: str = ""
    trailing_trivia: str = ""
    insert_before_line: int = 1
    insert_after_line: int = 1
    table_name: Optional[str] = None
    dotted_path: Tuple[str, ...] = ()
    is_array_table: bool = False

    @property
    def line_start(self) -> int:
        return self.source_line

    @property
    def line_end(self) -> int:
        return self.end_line


def _new_id() -> str:
    return str(uuid.uuid4())


def _split_comment(text: str) -> Tuple[str, str]:
    """Split a TOML comment while ignoring # characters inside strings."""
    quote: Optional[str] = None
    escaped = False
    for index, char in enumerate(text):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                quote = None
        elif char in ('"', "'"):
            quote = char
        elif char == "#":
            return text[:index].rstrip(), text[index:]
    return text.rstrip(), ""


def _split_assignment(content: str) -> Optional[Tuple[str, str, str, str]]:
    quote: Optional[str] = None
    escaped = False
    for index, char in enumerate(content):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                quote = None
        elif char in ('"', "'"):
            quote = char
        elif char == "=":
            left = content[:index]
            key = left.strip()
            if not key:
                return None
            prefix = left[: len(left) - len(left.lstrip())]
            value, suffix = _split_comment(content[index + 1 :])
            return key, prefix, value.strip(), suffix
    return None


def _tree_value(value: Any) -> TreeNode:
    if value is None:
        kind: TreeNodeType = "null"
        return TreeNode(stable_id=_new_id(), type=kind, value=None)
    if isinstance(value, bool):
        return TreeNode(stable_id=_new_id(), type="boolean", value=value)
    if isinstance(value, (int, float)):
        return TreeNode(stable_id=_new_id(), type="number", value=value)
    if isinstance(value, str):
        return TreeNode(stable_id=_new_id(), type="string", value=value)
    if isinstance(value, list):
        return TreeNode(
            stable_id=_new_id(),
            type="array",
            value=None,
            children=[_tree_value(item) for item in value],
        )
    if isinstance(value, dict):
        children: List[TreeNode] = []
        for key, item in value.items():
            child = _tree_value(item)
            child.key = str(key)
            children.append(child)
        return TreeNode(stable_id=_new_id(), type="object", value=None, children=children)
    raise ValueError(f"Unsupported TOML value type: {type(value).__name__}")


def _decode_value(raw_value: str) -> Any:
    try:
        return tomllib.loads("value = " + raw_value)["value"]
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid TOML value: {exc}") from exc


_TABLE_RE = re.compile(r"^[ \t]*(\[\[?)([^\]]+)(\]\]?)[ \t]*$")


def parse_toml_source(source_text: str) -> List[TreeNode]:
    """Parse TOML into one root container while retaining source trivia."""
    if not isinstance(source_text, str):
        raise TypeError("TOML source must be str")
    try:
        tomllib.loads(source_text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML: {exc}") from exc

    lines = source_text.splitlines(keepends=True)
    root = TomlConfigContainer(
        stable_id=_new_id(), type="object", value=None, children=[],
        source_line=1, end_line=max(1, len(lines)),
        insert_before_line=1, insert_after_line=len(lines) + 1,
    )
    current = root
    pending: List[str] = []
    last_content_line = 0
    for line_number, raw_line in enumerate(lines, start=1):
        content = raw_line.rstrip("\r\n")
        ending = raw_line[len(content) :]
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            pending.append(content)
            continue

        header_content, header_comment = _split_comment(content)
        table_match = _TABLE_RE.match(header_content)
        if table_match:
            current.end_line = max(current.end_line, line_number - 1)
            marker, name, _ = table_match.groups()
            table_name = name.strip()
            dotted_path = tuple(part.strip() for part in table_name.split("."))
            table = TomlConfigContainer(
                stable_id=_new_id(), type="object", key=table_name,
                value=None, children=[], source_line=line_number,
                end_line=line_number, raw_header=content,
                leading_trivia="\n".join(pending),
                insert_before_line=line_number, insert_after_line=line_number + 1,
                table_name=table_name, dotted_path=dotted_path,
                is_array_table=marker == "[[",
            )
            table.comment_before = "\n".join(pending) if pending else None
            table.comment_inline = header_comment or None
            pending.clear()
            root.children.append(table)
            current = table
            last_content_line = line_number
            continue

        assignment = _split_assignment(content)
        if assignment is None:
            raise ValueError(f"Invalid TOML: unsupported content on line {line_number}")
        key, prefix, raw_value, suffix = assignment
        node = _tree_value(_decode_value(raw_value))
        key_node = TomlConfigKey(
            stable_id=node.stable_id, type=node.type, key=key, value=node.value,
            children=node.children, comment_inline=suffix or None,
            source_line=line_number, end_line=line_number, raw_line=content,
            key_prefix=prefix, value_raw=raw_value, value_suffix=suffix,
            line_ending=ending, insert_before_line=line_number,
            insert_after_line=line_number + 1,
        )
        key_node.comment_before = "\n".join(pending) if pending else None
        pending.clear()
        current.children.append(key_node)
        current.end_line = line_number
        last_content_line = line_number

    if pending:
        current.trailing_trivia = "\n".join(pending)
        current.end_line = max(current.end_line, len(lines))
    root.end_line = max(root.end_line, last_content_line, len(lines))
    for child in root.children:
        if isinstance(child, TomlConfigContainer):
            child.insert_after_line = child.end_line + 1
    return [root]


parse_toml_source_to_roots = parse_toml_source
ConfigKey = TomlConfigKey
ConfigContainer = TomlConfigContainer

__all__ = [
    "ConfigContainer", "ConfigKey", "TomlConfigContainer", "TomlConfigKey",
    "parse_toml_source", "parse_toml_source_to_roots",
]
