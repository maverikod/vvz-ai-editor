"""Lossless YAML reader for the format plugin (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: turning YAML *block* structure -- indentation, entries, scalars, block
scalars, trivia and document markers -- into common-model nodes without losing
a single byte. :class:`YamlReader` inherits the flow-collection reader from
:mod:`.flow`, so one object reads both syntaxes; node construction lives in
:mod:`.builder` and the lexical predicates in :mod:`.scanner`. This module
does not implement the plugin contract and never renders anything back --
``plugin.py`` and ``emitter.py`` own those.

The byte-fidelity scheme ({p022}) is the whole design. Every byte of the
source ends up owned by exactly one node:

* trivia and scalars store their own text verbatim in ``fields["raw"]``;
* every entry and every flow container stores the text before its value in
  ``fields["head"]`` and the text after it in ``fields["tail"]``.

So a node renders as ``head + rendered children + tail``, the concatenation of
a whole tree reproduces the source exactly, and -- unlike a scheme that stores
one raw blob per subtree -- editing a nested node really does change the
output, because each ancestor's text is assembled from its live children
rather than replayed from a stale copy.

Trivia lines become nodes of their own, attached to the innermost block open
at that point. Which block owns a comment is a semantic nicety; the rendered
order, and therefore byte identity, is the same either way.

Source-of-truth requirement labels honored here: {p013}, {p022}, {p049},
{p097}.
"""

from __future__ import annotations

import bisect
from types import MappingProxyType
from typing import List, Optional, Tuple

from tree_engine.core.nodes import Node
from tree_engine.plugins.yaml.builder import NodeBuilder
from tree_engine.plugins.yaml.flow import ANCHOR_MESSAGE, FlowReader
from tree_engine.plugins.yaml.scanner import (
    BLOCK_HEADER_RE, ENTRY_KINDS, FLOW_OPENERS, KIND_BLANK, KIND_BLOCK, KIND_COMMENT,
    KIND_ITEM, KIND_MAPPING, KIND_MARKER, KIND_PAIR, KIND_SCALAR, KIND_SEQUENCE,
    KIND_TRIVIA, NO_TRANSLATION, decode_block, decode_scalar, find_colon, indent_of,
    is_marker, is_trivia, scan_quoted, starts_item, syntax, unsupported,
)

__all__ = ["patch_head", "YamlReader"]


def patch_head(node: Node, marker: str, width: int) -> Node:
    """Give a compact ``- key: value`` marker back to its deepest first entry.

    To read the compact form the reader rewrites the ``- `` marker to spaces,
    so the nested block sees a normally indented first line and needs no
    special case. That rewrite must not reach the tree, so this puts the
    original marker text back on the first entry that actually owns a head --
    recursing through nested compact items such as ``- - a``, whose outer item
    holds no head of its own. Identity is preserved: the rebuilt node keeps
    its ``node_id`` and ``short_id``.
    """

    fields, children = node.fields, node.children
    if node.kind in ENTRY_KINDS and fields.get("head"):
        merged = dict(fields)
        merged["head"] = marker + str(fields["head"])[width:]
        fields = MappingProxyType(merged)
    elif children:
        children = (patch_head(children[0], marker, width),) + children[1:]
    else:
        return node
    return Node(kind=node.kind, fields=fields, children=children,
                node_id=node.node_id, short_id=node.short_id)


class YamlReader(FlowReader):
    """Reads one YAML source text into common-model nodes.

    The reader works on two coordinate systems at once: a list of lines with
    their terminators, for block structure and indentation, and the original
    flat text with a per-line start offset table, for constructs that may run
    past a line end (quoted scalars, continued plain scalars, multi-line flow
    collections). Nothing but common-model nodes ever leaves this class, so no
    internal representation can cross the plugin boundary.
    """

    def __init__(self, text: str, builder: NodeBuilder) -> None:
        self.text = text
        self.lines = text.splitlines(keepends=True)
        self.count = len(self.lines)
        self.builder = builder
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))
        for number, line in enumerate(self.lines, start=1):
            if line.strip() and "\t" in line[:indent_of(line) + 1]:
                raise syntax("tab character in indentation", number)

    # -- shared position helpers ------------------------------------------

    def _span(self, first: int, begin: int, node: Node, end: int) -> Tuple[str, Node, str, int]:
        """Wrap a value that occupies ``begin``..``end`` into an entry's parts.

        ``first`` is the line the owning entry starts on, which is not always
        the line the value starts on: a plain scalar written under its key
        begins further down, and every byte in between -- the line break, any
        trivia, the indentation -- stays in the head.
        """

        row = min(bisect.bisect_right(self.starts, end) - 1, self.count - 1)
        tail = self.text[end:self.starts[row] + len(self.lines[row])]
        return self.text[self.starts[first]:begin], node, tail, row + 1

    # -- block structure ---------------------------------------------------

    def read_stream(self) -> List[Node]:
        """Read the whole line stream into the top-level document children."""

        children: List[Node] = []
        index = 0
        while index < self.count:
            if is_marker(self.lines[index]):
                children.append(self.builder.node(KIND_MARKER, {"raw": self.lines[index]}))
                index += 1
                continue
            block, after = self.read_block(index, -1)
            if after == index:
                raise syntax("cannot classify line", index + 1)
            children.append(block)
            index = after
        return children

    def _next_entry(self, index: int) -> Optional[int]:
        """Return the index of the first non-trivia line at/after ``index``."""

        while index < self.count and is_trivia(self.lines[index]):
            index += 1
        return index if index < self.count else None

    def read_block(self, index: int, min_indent: int, seq_equal: bool = False) -> Tuple[Node, int]:
        """Read one indentation block: its entries plus the trivia between them.

        The first entry fixes the block's indentation. ``seq_equal`` marks the
        YAML form where a sequence sits at the same indentation as the key it
        belongs to, in which case a same-indent line that is not a ``-`` entry
        ends the block rather than joining it.
        """

        children: List[Node] = []
        block_indent: Optional[int] = None
        kind: Optional[str] = None
        while index < self.count:
            line = self.lines[index]
            if is_marker(line):
                break
            if is_trivia(line):
                trivia = KIND_BLANK if not line.strip() else KIND_COMMENT
                children.append(self.builder.node(trivia, {"raw": line}))
                index += 1
                continue
            indent = indent_of(line)
            if block_indent is None:
                if indent < min_indent or (indent == min_indent
                                           and not (seq_equal and starts_item(line, indent))):
                    break
                block_indent = indent
            elif indent < block_indent:
                break
            elif seq_equal and not starts_item(line, indent):
                break  # a same-indent sequence ends where its parent mapping resumes
            elif indent > block_indent:
                raise syntax("unexpected indentation", index + 1)
            entry, index = self.read_entry(index, block_indent)
            entry_kind = KIND_SEQUENCE if entry.kind == KIND_ITEM else KIND_MAPPING
            if kind is None:
                kind = entry_kind
            elif kind != entry_kind:
                raise syntax("mapping and sequence entries in one block", index)
            children.append(entry)
        return self.builder.node(kind or KIND_TRIVIA, {}, children), index

    def read_entry(self, index: int, indent: int) -> Tuple[Node, int]:
        """Read one mapping pair or one sequence item together with its value."""

        line = self.lines[index]
        if starts_item(line, indent):
            head, value, tail, after = self.read_value(index, indent + 1, indent, False, True)
            kind, fields = KIND_ITEM, {"head": head, "tail": tail}
        else:
            key_raw, colon = self._scan_key(line, indent, index + 1)
            head, value, tail, after = self.read_value(index, colon + 1, indent, True, False)
            kind = KIND_PAIR
            fields = {"key": decode_scalar(key_raw), "key_raw": key_raw,
                      "head": head, "tail": tail}
        return self.builder.node(kind, fields, (value,) if value is not None else ()), after

    def _scan_key(self, line: str, start: int, number: int) -> Tuple[str, int]:
        """Return a block mapping key's source text and its ``:`` separator index."""

        if line[start] in NO_TRANSLATION:
            raise unsupported("Anchored", f"YAML indicator {line[start]!r} {ANCHOR_MESSAGE}")
        if line[start] in FLOW_OPENERS:
            raise unsupported("FlowKey", "a flow collection used as a block mapping key "
                                         "is outside this plugin's subset")
        if line[start] in "\"'":
            end = index = scan_quoted(line, start, number)
            while index < len(line) and line[index] == " ":
                index += 1
            if index >= len(line) or line[index] != ":":
                raise syntax("expected ':' after a quoted mapping key", number)
            return line[start:end], index
        colon = find_colon(line, start)
        if colon < 0:
            raise syntax("expected a mapping or sequence entry", number)
        key_raw = line[start:colon].rstrip(" ")
        if not key_raw:
            raise syntax("empty mapping key", number)
        if key_raw.startswith("<<"):
            raise unsupported("MergeKey", "YAML merge keys ('<<') cannot round-trip faithfully")
        return key_raw, colon

    def read_value(self, index: int, start: int, indent: int, allow_same: bool,
                   compact: bool) -> Tuple[str, Optional[Node], str, int]:
        """Read one entry's value as ``(head, value, tail, next_index)``.

        ``start`` is the column just past the ``:`` or ``-`` that introduced
        the value. ``allow_same`` permits a block sequence at the entry's own
        indentation (legal only under a mapping key); ``compact`` permits the
        ``- key: value`` form (legal only for a sequence item).
        """

        line = self.lines[index]
        rest = line[start:]
        if not rest.strip() or rest.lstrip(" ").startswith("#"):
            return self._value_below(index, indent, allow_same, line)
        position = start
        while position < len(line) and line[position] == " ":
            position += 1
        char = line[position]
        if char in NO_TRANSLATION:
            raise unsupported("Anchored", f"YAML indicator {char!r} {ANCHOR_MESSAGE}")
        if char in FLOW_OPENERS:
            begin = self.starts[index] + position
            node, end = self.read_flow(begin)
            return self._span(index, begin, node, end)
        if char in "|>":
            return self._read_block_scalar(index, position, indent)
        if compact and (starts_item(line, position) or find_colon(line, position) >= 0):
            marker = line[:position]
            self.lines[index] = " " * position + line[position:]
            block, after = self.read_block(index, position - 1)
            return "", patch_head(block, marker, position), "", after
        return self._scalar_value(index, index, position, indent)

    def _value_below(self, index: int, indent: int, allow_same: bool,
                     line: str) -> Tuple[str, Optional[Node], str, int]:
        """Resolve an entry whose line ends after the ``:`` or ``-``.

        What follows is a nested block, a plain scalar written on the lines
        below, or nothing at all (a null value).
        """

        nxt = self._next_entry(index + 1)
        if nxt is not None and not is_marker(self.lines[nxt]):
            deeper = indent_of(self.lines[nxt])
            entry = self.lines[nxt]
            same = allow_same and deeper == indent and starts_item(entry, deeper)
            if same or (deeper > indent and (starts_item(entry, deeper)
                                             or find_colon(entry, deeper) >= 0)):
                block, after = self.read_block(index + 1, indent, same)
                return line, block, "", after
            if deeper > indent:
                return self._scalar_value(index, nxt, deeper, indent)
        return line, None, "", index + 1

    def _scalar_value(self, first: int, index: int, start: int,
                      indent: int) -> Tuple[str, Node, str, int]:
        """Build a scalar value node whose head reaches back to line ``first``."""

        begin = self.starts[index] + start
        raw, end = self._read_scalar(index, start, indent)
        fields = {"raw": raw, "value": decode_scalar(raw),
                  "style": raw[0] if raw[0] in "\"'" else "plain"}
        return self._span(first, begin, self.builder.node(KIND_SCALAR, fields), end)

    def _plain_end(self, start: int) -> int:
        """Return the end offset of one plain-scalar line segment from ``start``."""

        end = start
        while end < len(self.text):
            char = self.text[end]
            if char == "\n" or (char == "#" and end > start and self.text[end - 1] == " "):
                break
            end += 1
        while end > start and self.text[end - 1] in " \r":
            end -= 1
        return end

    def _read_scalar(self, index: int, start: int, indent: int) -> Tuple[str, int]:
        """Read one inline scalar at line ``index``, column ``start``.

        Returns its verbatim source text and its absolute end offset. A quoted
        scalar may run past the line end. A plain scalar absorbs every
        following line that is more indented than ``indent`` and is not itself
        an entry, a marker, or trivia -- YAML's multi-line plain scalar.
        """

        begin = self.starts[index] + start
        if self.text[begin] in "\"'":
            end = scan_quoted(self.text, begin, index + 1)
            return self.text[begin:end], end
        end = self._plain_end(begin)
        if end == begin:
            raise syntax("empty scalar value", index + 1)
        while True:
            newline = self.text.find("\n", end)
            if newline < 0 or self.text[end:newline].strip():
                break  # a trailing comment ends the scalar; only spaces may follow
            row = bisect.bisect_right(self.starts, newline)
            if row >= self.count or is_trivia(self.lines[row]) or is_marker(self.lines[row]):
                break
            below, line = indent_of(self.lines[row]), self.lines[row]
            if below < indent or (below == indent and (starts_item(line, below)
                                                       or find_colon(line, below) >= 0)):
                break  # a sibling entry, not a continuation of this scalar
            head = self.starts[row] + below
            stop = self._plain_end(head)
            if stop == head:
                break
            end = stop
        return self.text[begin:end], end

    def _read_block_scalar(self, index: int, start: int,
                           indent: int) -> Tuple[str, Node, str, int]:
        """Read a ``|``/``>`` header line plus every body line it owns."""

        line = self.lines[index]
        header = line[start:].rstrip("\r\n").rstrip(" ")
        comment = header.find(" #")
        if comment >= 0:
            header = header[:comment].rstrip(" ")
        if not BLOCK_HEADER_RE.fullmatch(header):
            raise unsupported("BlockScalar", f"unsupported block scalar header {header!r}")
        body: List[str] = []
        cursor = index + 1
        while cursor < self.count and (not self.lines[cursor].strip()
                                       or indent_of(self.lines[cursor]) > indent):
            body.append(self.lines[cursor])
            cursor += 1
        if not header.endswith("+"):  # trailing blanks are the enclosing block's trivia
            while body and not body[-1].strip():
                body.pop()
                cursor -= 1
        fields = {"raw": "".join(body), "style": header,
                  "value": decode_block(header, body, indent)}
        return line, self.builder.node(KIND_BLOCK, fields), "", cursor
