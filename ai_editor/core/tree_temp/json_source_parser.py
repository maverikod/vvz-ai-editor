"""
Tolerant JSON SourceParser: text to TreeNode forest with comment fields (C-005, C-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from ai_editor.core.tree_temp.tree_node import TreeNode, TreeNodeType

_ESC_CH = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}  # fmt: skip


def _comment_text(source_text: str, span: Tuple[int, int]) -> str:
    start, end = span
    return source_text[start:end]


def _before_comment_ok(s: str, line_begin: int, i: int) -> bool:
    j = line_begin
    while j < i and s[j] in " \t\r":
        j += 1
    if j == i:
        return True
    if s[j] in "{[,":
        k = j + 1
        while k < i and s[k] in " \t\r":
            k += 1
        return k == i
    return False


@dataclass
class _Lexer:
    s: str
    n: int = field(init=False)
    i: int = 0
    line_begin: int = 0

    def __post_init__(self) -> None:
        self.n = len(self.s)

    def _peek(self) -> str:
        return "" if self.i >= self.n else self.s[self.i]

    def _eof(self) -> bool:
        return self.i >= self.n

    def _advance(self) -> None:
        if self.i < self.n:
            if self.s[self.i] == "\n":
                self.line_begin = self.i + 1
            self.i += 1

    def _read_line_comment(self) -> Tuple[int, int]:
        start = self.i
        while not self._eof() and self._peek() != "\n":
            self._advance()
        return start, self.i

    def _read_block_comment(self) -> Tuple[int, int]:
        start = self.i
        self.i += 2
        while self.i < self.n - 1:
            if self.s[self.i] == "*" and self.s[self.i + 1] == "/":
                self.i += 2
                return start, self.i
            if self.s[self.i] == "\n":
                self.line_begin = self.i + 1
            self.i += 1
        raise ValueError("Invalid tolerant JSON: unclosed block comment")

    def _same_line_has_more_tokens(self) -> bool:
        j = self.i
        while j < self.n and self.s[j] in " \t\r":
            j += 1
        return j < self.n and self.s[j] != "\n"


class _Parser:
    def __init__(self, source_text: str) -> None:
        self.s = source_text
        self.lex = _Lexer(source_text)
        self.pending_before: Optional[str] = None

    def _append_pending(self, text: str) -> None:
        if self.pending_before is None:
            self.pending_before = text
        else:
            self.pending_before = self.pending_before + "\n" + text

    def _skip_ws(self) -> None:
        while not self.lex._eof():
            c = self.lex._peek()
            if c in " \t":
                self.lex._advance()
                continue
            if c == "\r":
                self.lex._advance()
                continue
            if c == "\n":
                self.lex._advance()
                continue
            if _before_comment_ok(self.s, self.lex.line_begin, self.lex.i):
                if self.s.startswith("//", self.lex.i):
                    span = self.lex._read_line_comment()
                elif self.s.startswith("/*", self.lex.i):
                    span = self.lex._read_block_comment()
                else:
                    break
                self._append_pending(_comment_text(self.s, span))
                continue
            break

    def _skip_horizontal_ws(self) -> None:
        while not self.lex._eof() and self.lex._peek() in " \t\r":
            self.lex._advance()

    def _expect(self, ch: str) -> None:
        if self.lex._peek() != ch:
            raise ValueError(f"Invalid tolerant JSON: expected {ch!r}")
        self.lex._advance()

    def _attach_pending(self, node: TreeNode) -> None:
        if self.pending_before is not None:
            node.comment_before = self.pending_before
            self.pending_before = None

    def _try_inline_comment(self, node: TreeNode) -> None:
        if not self.lex._same_line_has_more_tokens():
            return
        saved_i, saved_lb = self.lex.i, self.lex.line_begin
        self._skip_horizontal_ws()
        if self.lex._same_line_has_more_tokens():
            if self.s.startswith("//", self.lex.i):
                node.comment_inline = _comment_text(
                    self.s, self.lex._read_line_comment()
                )
            elif self.s.startswith("/*", self.lex.i):
                node.comment_inline = _comment_text(
                    self.s, self.lex._read_block_comment()
                )
            else:
                self.lex.i, self.lex.line_begin = saved_i, saved_lb
        else:
            self.lex.i, self.lex.line_begin = saved_i, saved_lb

    def _parse_string_raw(self) -> Tuple[str, int, int]:
        start_outer = self.lex.i
        self._expect('"')
        chunks: List[str] = []
        while not self.lex._eof():
            c = self.lex._peek()
            if c == '"':
                self.lex._advance()
                return "".join(chunks), start_outer, self.lex.i
            if ord(c) < 0x20:
                raise ValueError("Invalid tolerant JSON: control character in string")
            if c != "\\":
                chunks.append(c)
                self.lex._advance()
                continue
            self.lex._advance()
            if self.lex._eof():
                raise ValueError("Invalid tolerant JSON: string ends after backslash")
            esc = self.lex._peek()
            self.lex._advance()
            if esc in _ESC_CH:
                chunks.append(_ESC_CH[esc])
            elif esc == "u":
                if self.lex.i + 4 > self.lex.n:
                    raise ValueError("Invalid tolerant JSON: short \\u escape")
                hex_part = self.s[self.lex.i : self.lex.i + 4]
                self.lex.i += 4
                try:
                    chunks.append(chr(int(hex_part, 16)))
                except ValueError as exc:
                    raise ValueError("Invalid tolerant JSON: bad \\u escape") from exc
            else:
                raise ValueError("Invalid tolerant JSON: bad string escape")
        raise ValueError("Invalid tolerant JSON: unterminated string")

    def _parse_number_node(self) -> TreeNode:
        start = self.lex.i
        if self.lex._peek() == "-":
            self.lex._advance()
        c = self.lex._peek()
        if c == "0":
            self.lex._advance()
            if self.lex._peek().isdigit():
                raise ValueError("Invalid tolerant JSON: bad number")
        elif c.isdigit():
            self.lex._advance()
            while self.lex._peek().isdigit():
                self.lex._advance()
        else:
            raise ValueError("Invalid tolerant JSON: bad number")
        if self.lex._peek() == ".":
            self.lex._advance()
            if not self.lex._peek().isdigit():
                raise ValueError("Invalid tolerant JSON: bad fraction")
            while self.lex._peek().isdigit():
                self.lex._advance()
        if self.lex._peek() in "eE":
            self.lex._advance()
            if self.lex._peek() in "+-":
                self.lex._advance()
            if not self.lex._peek().isdigit():
                raise ValueError("Invalid tolerant JSON: bad exponent")
            while self.lex._peek().isdigit():
                self.lex._advance()
        raw = self.s[start : self.lex.i]
        val: Any = float(raw) if any(ch in raw for ch in ".eE") else int(raw)
        return TreeNode(stable_id=str(uuid.uuid4()), type="number", value=val)

    def _parse_keyword(
        self, word: str, node_type: TreeNodeType, pyval: Any
    ) -> TreeNode:
        if not self.s.startswith(word, self.lex.i):
            raise ValueError(f"Invalid tolerant JSON: expected {word!r}")
        self.lex.i += len(word)
        if not self.lex._eof() and (
            self.lex._peek().isalnum() or self.lex._peek() == "_"
        ):
            raise ValueError("Invalid tolerant JSON: unexpected token")
        return TreeNode(stable_id=str(uuid.uuid4()), type=node_type, value=pyval)

    def _parse_value(self) -> TreeNode:
        self._skip_ws()
        if self.lex._eof():
            raise ValueError("Invalid tolerant JSON: value expected")
        c = self.lex._peek()
        if c == "{":
            return self._parse_object()
        if c == "[":
            return self._parse_array_container()
        if c == '"':
            pystr, _, _ = self._parse_string_raw()
            node = TreeNode(stable_id=str(uuid.uuid4()), type="string", value=pystr)
            self._attach_pending(node)
            self._try_inline_comment(node)
            return node
        if c == "-" or c.isdigit():
            node = self._parse_number_node()
            self._attach_pending(node)
            self._try_inline_comment(node)
            return node
        if self.s.startswith("true", self.lex.i):
            node = self._parse_keyword("true", "boolean", True)
            self._attach_pending(node)
            self._try_inline_comment(node)
            return node
        if self.s.startswith("false", self.lex.i):
            node = self._parse_keyword("false", "boolean", False)
            self._attach_pending(node)
            self._try_inline_comment(node)
            return node
        if self.s.startswith("null", self.lex.i):
            node = self._parse_keyword("null", "null", None)
            self._attach_pending(node)
            self._try_inline_comment(node)
            return node
        raise ValueError("Invalid tolerant JSON: unexpected token")

    def _parse_object(self) -> TreeNode:
        self._expect("{")
        obj_children: List[TreeNode] = []
        obj = TreeNode(
            stable_id=str(uuid.uuid4()),
            type="object",
            value=None,
            children=obj_children,
        )
        self._attach_pending(obj)
        self._skip_ws()
        if self.lex._peek() == "}":
            self.lex._advance()
            self._try_inline_comment(obj)
            return obj
        while True:
            self._skip_ws()
            if self.lex._peek() != '"':
                raise ValueError("Invalid tolerant JSON: object key must be string")
            key, _, _ = self._parse_string_raw()
            self._skip_ws()
            self._expect(":")
            child = self._parse_value()
            child.key = key
            obj_children.append(child)
            self._skip_ws()
            if self.lex._peek() == ",":
                self.lex._advance()
                continue
            if self.lex._peek() == "}":
                self.lex._advance()
                break
            raise ValueError("Invalid tolerant JSON: object delimiter expected")
        self._try_inline_comment(obj)
        return obj

    def _parse_array_container(self) -> TreeNode:
        self._expect("[")
        arr_children: List[TreeNode] = []
        arr = TreeNode(
            stable_id=str(uuid.uuid4()),
            type="array",
            value=None,
            children=arr_children,
        )
        self._attach_pending(arr)
        self._skip_ws()
        if self.lex._peek() == "]":
            self.lex._advance()
            self._try_inline_comment(arr)
            return arr
        while True:
            self._skip_ws()
            arr_children.append(self._parse_value())
            self._skip_ws()
            if self.lex._peek() == ",":
                self.lex._advance()
                continue
            if self.lex._peek() == "]":
                self.lex._advance()
                break
            raise ValueError("Invalid tolerant JSON: array delimiter expected")
        self._try_inline_comment(arr)
        return arr

    def _finish_doc(self) -> None:
        self._skip_ws()
        if self.pending_before is not None:
            raise ValueError(
                "Invalid tolerant JSON: trailing comment without following value"
            )
        if not self.lex._eof():
            raise ValueError("Invalid tolerant JSON: trailing data after document")

    def parse_document(self) -> List[TreeNode]:
        self._skip_ws()
        if self.lex._eof():
            raise ValueError("Invalid tolerant JSON: empty document")
        c = self.lex._peek()
        if c == "{":
            out = [self._parse_object()]
            self._finish_doc()
            return out
        if c == "[":
            self.lex._advance()
            self._skip_ws()
            if self.lex._peek() == "]":
                self.lex._advance()
                self._finish_doc()
                return []
            roots: List[TreeNode] = []
            while True:
                self._skip_ws()
                roots.append(self._parse_value())
                self._skip_ws()
                if self.lex._peek() == ",":
                    self.lex._advance()
                    continue
                if self.lex._peek() == "]":
                    self.lex._advance()
                    break
                raise ValueError("Invalid tolerant JSON: array delimiter expected")
            self._finish_doc()
            return roots
        out = [self._parse_value()]
        self._finish_doc()
        return out


def parse_json_source(source_text: str) -> List[TreeNode]:
    """Parse UTF-8 tolerant JSON text into root-level TreeNode list (C-005).

    Raises:
        ValueError: with message starting \"Invalid tolerant JSON:\" when the grammar cannot be parsed.
    """
    parser = _Parser(source_text)
    try:
        return parser.parse_document()
    except ValueError as e:
        msg = str(e)
        if not msg.startswith("Invalid tolerant JSON:"):
            raise ValueError(f"Invalid tolerant JSON: {msg}") from e
        raise
