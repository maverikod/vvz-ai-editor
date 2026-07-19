"""Round-trip oriented INI parser for the tree-temp configuration model.

INI has no standard AST, so the parser keeps the semantic value in ``TreeNode``
fields and stores the source details needed by a future serializer on the
specialised configuration nodes.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ai_editor.core.tree_temp.tree_node import TreeNode


_SECTION_RE = re.compile(r"^[ \t]*\[([^]]+)\][ \t]*(?:[;#].*)?$")


@dataclass
class ConfigKey(TreeNode):
    """One INI key/value line represented as a tree-temp scalar node."""

    source_line: int = 0
    end_line: int = 0
    raw_line: str = ""
    key_prefix: str = ""
    separator: str = "="
    value_suffix: str = ""
    insert_before_line: int = 0
    insert_after_line: int = 0

    @property
    def line_start(self) -> int:
        return self.source_line

    @property
    def line_end(self) -> int:
        return self.end_line


@dataclass
class ConfigContainer(TreeNode):
    """Document or section container with source and insertion anchors."""

    source_line: int = 1
    end_line: int = 0
    raw_header: str = ""
    leading_trivia: str = ""
    trailing_trivia: str = ""
    insert_before_line: int = 1
    insert_after_line: int = 1
    section_name: Optional[str] = None

    @property
    def line_start(self) -> int:
        return self.source_line

    @property
    def line_end(self) -> int:
        return self.end_line


def _new_id() -> str:
    return str(uuid.uuid4())


def _split_inline_comment(value: str) -> Tuple[str, str]:
    """Split a comment only when it is separated from the value by whitespace."""
    for index, char in enumerate(value):
        if char not in "#;" or index == 0 or not value[index - 1].isspace():
            continue
        return value[:index].rstrip(), value[index:]
    return value.rstrip(), ""


def _key_parts(line: str) -> Optional[Tuple[str, str, str, str, str]]:
    """Return key formatting parts, or ``None`` for non-key content."""
    content = line.rstrip("\r\n")
    if not content.strip() or content.lstrip().startswith(("#", ";", "[")):
        return None
    match = re.match(r"^(.*?)(=|:)(.*)$", content)
    if match is None:
        return None
    left, separator, raw_value = match.groups()
    key = left.strip()
    if not key:
        return None
    prefix = left[: len(left) - len(left.lstrip())]
    value, suffix = _split_inline_comment(raw_value)
    value = value.strip()
    return key, prefix, separator, value, suffix


def _attach_trivia(node: TreeNode, trivia: List[str]) -> None:
    if trivia:
        node.comment_before = "\n".join(trivia)


def parse_ini_source(source_text: str) -> List[TreeNode]:
    """Parse INI text into one root ``ConfigContainer``.

    Root-level keys are direct children of the root.  Each section is an
    object-compatible ``ConfigContainer`` child whose keyed children are the
    section's entries.  Values remain strings because INI has no scalar type
    system, while comments and blank-line trivia are retained on the nodes.
    """
    if not isinstance(source_text, str):
        raise TypeError("INI source must be str")

    lines = source_text.splitlines(keepends=True)
    root = ConfigContainer(
        stable_id=_new_id(),
        type="object",
        value=None,
        children=[],
        source_line=1,
        end_line=max(1, len(lines)),
        insert_before_line=1,
        insert_after_line=len(lines) + 1,
        section_name=None,
    )
    current: ConfigContainer = root
    pending: List[str] = []
    last_content_line = 0

    for line_number, raw_line in enumerate(lines, start=1):
        content = raw_line.rstrip("\r\n")
        stripped = content.strip()
        if not stripped or stripped.startswith(("#", ";")):
            pending.append(content)
            continue

        section_match = _SECTION_RE.match(content)
        if section_match is not None:
            section_name = section_match.group(1).strip()
            section = ConfigContainer(
                stable_id=_new_id(),
                type="object",
                key=section_name,
                value=None,
                children=[],
                source_line=line_number,
                end_line=line_number,
                raw_header=content,
                leading_trivia="\n".join(pending),
                insert_before_line=line_number,
                insert_after_line=line_number + 1,
                section_name=section_name,
            )
            _attach_trivia(section, pending)
            pending.clear()
            root.children.append(section)
            current = section
            last_content_line = line_number
            continue

        parts = _key_parts(content)
        if parts is None:
            raise ValueError(f"Invalid INI: unsupported content on line {line_number}")
        key, prefix, separator, value, suffix = parts
        node = ConfigKey(
            stable_id=_new_id(),
            type="string",
            key=key,
            value=value,
            children=None,
            comment_inline=suffix or None,
            source_line=line_number,
            end_line=line_number,
            raw_line=content,
            key_prefix=prefix,
            separator=separator,
            value_suffix=suffix,
            insert_before_line=line_number,
            insert_after_line=line_number + 1,
        )
        _attach_trivia(node, pending)
        pending.clear()
        current.children.append(node)
        current.end_line = line_number
        last_content_line = line_number

    if pending:
        # EOF trivia belongs to the active container.  This keeps comments and
        # blank lines after the last section key with that section's serializer
        # region instead of moving them to the document root.
        current.trailing_trivia = "\n".join(pending)
        current.end_line = max(current.end_line, len(lines))
    root.end_line = max(root.end_line, last_content_line, len(lines))
    for child in root.children:
        if isinstance(child, ConfigContainer):
            child.insert_after_line = child.end_line + 1
    return [root]


parse_ini_source_to_roots = parse_ini_source

__all__ = ["ConfigContainer", "ConfigKey", "parse_ini_source", "parse_ini_source_to_roots"]
