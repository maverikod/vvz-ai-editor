"""The YAML format plugin (concept C-016, atomic step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``FormatPluginContract`` + CORE-side ``FormatBoundary`` for ``format_id="yaml"``
(``.yaml``/``.yml``), standalone on the standard library and sibling
``tree_engine`` modules only -- no third-party YAML library.

Byte fidelity ({p022}) is the primary contract, so this module carries its own
block-structure reader rather than delegating to a general YAML library. Every
source line is owned by exactly one node as verbatim text -- ``raw`` on trivia
and scalars, ``head``/``tail`` on entries -- so an entry renders as exactly
``head + render(value) + tail`` and the tree renders bottom-up from real
per-node text: an edited subtree changes the output, an untouched one never
does. ``render_document(parse_document(raw)) == raw`` therefore holds across
the supported subset, preserving comments, blank lines, indentation width,
quoting style, block-scalar layout and document markers.

Supported subset: block mappings; block sequences, including the compact
``- key: value`` form and the same-indent form under a key; plain, single- and
double-quoted scalars, single-line or continued over following lines; literal
(``|``) and folded (``>``) block scalars with indent and chomping indicators;
full-line and trailing comments; blank lines; ``---``/``...`` markers.

``UNSUPPORTED_TRANSLATION`` covers anchors (``&``), aliases (``*``), tags
(``!``), explicit keys (``?``), merge keys (``<<``), flow collections
(``{``/``[``) and any common-model node this format cannot render. Damaged
input -- a tab in the indent, an unterminated quoted scalar, inconsistent
indentation, mixed mapping/sequence entries in one block, or a line that is
neither entry nor trivia (which includes a bare top-level scalar document,
outside this subset) -- is ``FORMAT_CONTENT_PARSE_FAILED`` for a document and
``FORMAT_FRAGMENT_PARSE_FAILED`` for a fragment. Every node carries a fresh
UUID4 ``node_id`` and a document-local ``short_id`` ({p013}, {p097}).

Labels honored here: {p022}, {p026}, {p049}, {p056}, {p060}, {p062}.
"""
from __future__ import annotations

import bisect
import json
import re
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.core.short_id import ShortIdMap
from tree_engine.exceptions import (
    FormatContentParseFailed, FormatFragmentParseFailed, FormatPluginContractError,
    UnsupportedTranslation,
)
from tree_engine.plugins.contract import (
    FormatPluginContract, FormatPluginMetadata, SemanticRoleMapping,
)

__all__ = ["FORMAT_ID", "YamlFormatPlugin", "YAML_FORMAT_PLUGIN"]

FORMAT_ID = "yaml"
(KIND_DOCUMENT, KIND_MAPPING, KIND_PAIR, KIND_SEQUENCE, KIND_ITEM, KIND_SCALAR,
 KIND_BLOCK, KIND_COMMENT, KIND_BLANK, KIND_MARKER, KIND_TRIVIA) = [
    f"{FORMAT_ID}:{n}" for n in ("Document", "Mapping", "Pair", "Sequence", "Item", "Scalar",
                                 "BlockScalar", "Comment", "Blank", "Marker", "Trivia")]
_CONTAINERS = (KIND_DOCUMENT, KIND_MAPPING, KIND_SEQUENCE, KIND_TRIVIA)
_RAW = (KIND_COMMENT, KIND_BLANK, KIND_MARKER, KIND_SCALAR, KIND_BLOCK)
_ENTRIES = (KIND_PAIR, KIND_ITEM)
_VALUES = (KIND_MAPPING, KIND_SEQUENCE, KIND_SCALAR, KIND_BLOCK)
_TRIVIA = (KIND_COMMENT, KIND_BLANK)
_NO_TRANSLATION = "&*!?"  # anchor, alias, tag, explicit key: no faithful round trip
_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID, aliases=("yml",), file_extensions=("yaml", "yml"),
    plugin_version="1.0.0", contract_version="1.0.0",
    capabilities={"semantic_role_mapping": True, "byte_identical_round_trip": True})
_ROLE_MAP = SemanticRoleMapping({})  # YAML models no function/method/class/module
_INT_RE = re.compile(r"[-+]?[0-9]+")
_FLOAT_RE = re.compile(
    r"[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.[0-9]*)(?:[eE][-+]?[0-9]+)?|[-+]?[0-9]+[eE][-+]?[0-9]+")
_BLOCK_RE = re.compile(r"[|>](?:[1-9][+-]?|[+-]?[1-9]?)")

class _YamlSyntaxError(Exception):
    """Module-private malformed-YAML signal; never crosses the plugin boundary."""

def _syntax(message: str, number: int) -> _YamlSyntaxError:
    return _YamlSyntaxError(f"{message} (line {number})")

def _unsupported(node_type: str, message: str) -> UnsupportedTranslation:
    return UnsupportedTranslation(message, node_type=node_type, format_id=FORMAT_ID)

def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(message, plugin_id=FORMAT_ID)

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

def _is_trivia(line: str) -> bool:
    return not line.strip() or line.lstrip(" ").startswith("#")

def _is_marker(line: str) -> bool:
    text = line.rstrip("\r\n")
    return text in ("---", "...") or text[:4] in ("--- ", "... ")

def _starts_item(line: str, indent: int) -> bool:
    """True when ``line`` carries a block-sequence ``-`` marker at ``indent``."""
    return (indent < len(line) and line[indent] == "-"
            and (indent + 1 >= len(line) or line[indent + 1] in " \t\r\n"))

def _find_colon(line: str, start: int) -> int:
    """Index of the ``key: value`` separator at/after ``start``, else ``-1``."""
    index = start
    if index < len(line) and line[index] in "\"'":
        try:
            index = _scan_quoted(line, index, 0)
        except _YamlSyntaxError:
            return -1
    while index < len(line):
        char = line[index]
        if char in "\r\n" or (char == "#" and index > start and line[index - 1] == " "):
            return -1
        if char == ":" and (index + 1 >= len(line) or line[index + 1] in " \r\n"):
            return index
        index += 1
    return -1

def _scan_quoted(text: str, start: int, number: int) -> int:
    """Return the index just past the quoted scalar beginning at ``start``."""
    quote, index = text[start], start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and quote == '"':
            index += 2
        elif char == quote:
            if quote == "'" and text[index + 1:index + 2] == "'":
                index += 2
                continue
            return index + 1
        else:
            index += 1
    raise _syntax("unterminated quoted scalar", number)

def _fold(text: str) -> str:
    """YAML flow folding: one line break becomes a space, each extra one a newline."""
    if "\n" not in text:
        return text
    folded = re.sub(r"[ \t]*\n(?:[ \t]*\n)+[ \t]*",
                    lambda m: "\x00" * (m.group(0).count("\n") - 1), text)
    return re.sub(r"[ \t]*\n[ \t]*", " ", folded).replace("\x00", "\n")

def _decode_scalar(raw: str) -> Union[str, int, float, bool, None]:
    """Decode a scalar's source text into a YAML 1.2 core-schema value."""
    if raw.startswith('"'):
        # A backslash before a line break suppresses that break entirely; every
        # other break folds first, so only real escapes reach the JSON decoder.
        body = _fold(re.sub(r"\\\n[ \t]*", "", raw[1:-1]))
        body = re.sub(r"(?<!\\)((?:\\\\)*)\\ ", r"\1 ", body)  # YAML-only "\ " escape
        try:
            return json.loads(f'"{body}"')
        except ValueError:
            return body
    raw = _fold(raw)
    if raw.startswith("'"):
        return raw[1:-1].replace("''", "'")
    lowered = raw.lower()
    if raw == "" or lowered in ("~", "null"):
        return None
    if lowered in ("true", "false"):
        return lowered == "true"
    if _INT_RE.fullmatch(raw):
        return int(raw, 10)
    return float(raw) if _FLOAT_RE.fullmatch(raw) else raw

def _decode_block(style: str, lines: Sequence[str], indent: int) -> str:
    """Decode a literal/folded block-scalar body, honoring indent and chomping."""
    digits = [char for char in style if char.isdigit()]
    chomp = "+" if "+" in style else ("-" if "-" in style else "")
    body = [line.rstrip("\n").rstrip("\r") for line in lines]
    width = (indent + int(digits[0])) if digits else next(
        (_indent_of(line) for line in body if line.strip()), 0)
    rows = [line[width:] if len(line) > width else "" for line in body]
    if style[0] == "|":
        text = "".join(row + "\n" for row in rows)
    else:
        pieces = rows[:1]
        for position in range(1, len(rows)):
            row, previous = rows[position], rows[position - 1]
            folded = row and previous and row[0] != " " and previous[0] != " "
            pieces.append((" " if folded else "\n") + row)
        text = ("".join(pieces) + "\n") if rows else ""
    core = text.rstrip("\n")
    if chomp:
        return core if chomp == "-" else text
    return core + "\n" if core else ""

class _NodeBuilder:
    """Builds schema-validated nodes carrying a UUID4 ``node_id`` and a ``short_id``."""
    def __init__(self) -> None:
        self.short_ids = ShortIdMap()

    def node(self, kind: str, fields: Optional[Mapping[str, Any]] = None,
             children: Sequence[Node] = ()) -> Node:
        valid = make_node(kind, dict(fields or {}), list(children))
        node_id = generate_node_id()
        return Node(kind=valid.kind, fields=valid.fields, children=valid.children,
                    node_id=node_id, short_id=self.short_ids.allocate(node_id))

def _patch_head(node: Node, marker: str, width: int) -> Node:
    """Give a compact ``- key: value`` marker back to its deepest first entry."""
    fields, children = node.fields, node.children
    if node.kind in _ENTRIES and fields.get("head"):
        merged = dict(fields)
        merged["head"] = marker + str(fields["head"])[width:]
        fields = MappingProxyType(merged)
    elif children:
        children = (_patch_head(children[0], marker, width),) + children[1:]
    else:
        return node
    return Node(kind=node.kind, fields=fields, children=children,
                node_id=node.node_id, short_id=node.short_id)

class _YamlReader:
    """Line-oriented reader for the supported YAML subset."""
    def __init__(self, text: str, builder: _NodeBuilder) -> None:
        self.text = text
        self.lines = text.splitlines(keepends=True)
        self.count = len(self.lines)
        self.builder = builder
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))
        for number, line in enumerate(self.lines, start=1):
            if line.strip() and "\t" in line[:_indent_of(line) + 1]:
                raise _syntax("tab character in indentation", number)

    def read_stream(self) -> List[Node]:
        """Read the whole line stream into the top-level document children."""
        children: List[Node] = []
        index = 0
        while index < self.count:
            if _is_marker(self.lines[index]):
                children.append(self.builder.node(KIND_MARKER, {"raw": self.lines[index]}))
                index += 1
                continue
            block, after = self.read_block(index, -1)
            if after == index:
                raise _syntax("cannot classify line", index + 1)
            children.append(block)
            index = after
        return children

    def _next_entry(self, index: int) -> Optional[int]:
        while index < self.count and _is_trivia(self.lines[index]):
            index += 1
        return index if index < self.count else None

    def read_block(self, index: int, min_indent: int, seq_equal: bool = False) -> Tuple[Node, int]:
        """Read one indentation block: its entries plus the trivia between them."""
        children: List[Node] = []
        block_indent: Optional[int] = None
        kind: Optional[str] = None
        while index < self.count:
            line = self.lines[index]
            if _is_marker(line):
                break
            if _is_trivia(line):
                trivia = KIND_BLANK if not line.strip() else KIND_COMMENT
                children.append(self.builder.node(trivia, {"raw": line}))
                index += 1
                continue
            indent = _indent_of(line)
            if block_indent is None:
                if indent < min_indent or (indent == min_indent
                                           and not (seq_equal and _starts_item(line, indent))):
                    break
                block_indent = indent
            elif indent < block_indent:
                break
            elif seq_equal and not _starts_item(line, indent):
                break  # a same-indent sequence ends where its parent mapping resumes
            elif indent > block_indent:
                raise _syntax("unexpected indentation", index + 1)
            entry, index = self.read_entry(index, block_indent)
            entry_kind = KIND_SEQUENCE if entry.kind == KIND_ITEM else KIND_MAPPING
            if kind is None:
                kind = entry_kind
            elif kind != entry_kind:
                raise _syntax("mapping and sequence entries in one block", index)
            children.append(entry)
        return self.builder.node(kind or KIND_TRIVIA, {}, children), index

    def read_entry(self, index: int, indent: int) -> Tuple[Node, int]:
        """Read one mapping pair or one sequence item together with its value."""
        line = self.lines[index]
        if _starts_item(line, indent):
            head, value, tail, after = self.read_value(index, indent + 1, indent, False, True)
            kind, fields = KIND_ITEM, {"head": head, "tail": tail}
        else:
            key_raw, colon = self._scan_key(line, indent, index + 1)
            head, value, tail, after = self.read_value(index, colon + 1, indent, True, False)
            kind = KIND_PAIR
            fields = {"key": _decode_scalar(key_raw), "key_raw": key_raw,
                      "head": head, "tail": tail}
        return self.builder.node(kind, fields, (value,) if value is not None else ()), after

    def _scan_key(self, line: str, start: int, number: int) -> Tuple[str, int]:
        """Return a mapping key's source text and the index of its ``:`` separator."""
        if line[start] in _NO_TRANSLATION:
            raise _unsupported("Anchored", f"YAML indicator {line[start]!r} "
                               "(anchor/alias/tag/explicit key) cannot round-trip")
        if line[start] in "\"'":
            end = index = _scan_quoted(line, start, number)
            while index < len(line) and line[index] == " ":
                index += 1
            if index >= len(line) or line[index] != ":":
                raise _syntax("expected ':' after a quoted mapping key", number)
            return line[start:end], index
        colon = _find_colon(line, start)
        if colon < 0:
            raise _syntax("expected a mapping or sequence entry", number)
        key_raw = line[start:colon].rstrip(" ")
        if not key_raw:
            raise _syntax("empty mapping key", number)
        if key_raw.startswith("<<"):
            raise _unsupported("MergeKey", "YAML merge keys ('<<') cannot round-trip faithfully")
        if key_raw[0] in _NO_TRANSLATION:
            raise _unsupported("Anchored",
                               f"YAML key indicator {key_raw[0]!r} is not representable")
        return key_raw, colon

    def read_value(self, index: int, start: int, indent: int, allow_same: bool,
                   compact: bool) -> Tuple[str, Optional[Node], str, int]:
        """Read one entry's value as ``(head, value, tail, next_index)``."""
        line = self.lines[index]
        rest = line[start:]
        if not rest.strip() or rest.lstrip(" ").startswith("#"):
            nxt = self._next_entry(index + 1)
            if nxt is not None and not _is_marker(self.lines[nxt]):
                deeper = _indent_of(self.lines[nxt])
                same = allow_same and deeper == indent and _starts_item(self.lines[nxt], deeper)
                entry = self.lines[nxt]
                if same or (deeper > indent and (_starts_item(entry, deeper)
                                                 or _find_colon(entry, deeper) >= 0)):
                    block, after = self.read_block(index + 1, indent, same)
                    return line, block, "", after
                if deeper > indent:  # a plain scalar continued on the lines below
                    return self._scalar_value(index, nxt, deeper, indent)
            return line, None, "", index + 1
        position = start
        while position < len(line) and line[position] == " ":
            position += 1
        char = line[position]
        if char in _NO_TRANSLATION:
            raise _unsupported("Anchored", f"YAML indicator {char!r} "
                               "(anchor/alias/tag/explicit key) cannot round-trip")
        if char in "{[":
            raise _unsupported("FlowCollection", "YAML flow collections are outside this subset")
        if char in "|>":
            return self._read_block_scalar(index, position, indent)
        if compact and (_starts_item(line, position) or _find_colon(line, position) >= 0):
            marker = line[:position]
            self.lines[index] = " " * position + line[position:]
            block, after = self.read_block(index, position - 1)
            return "", _patch_head(block, marker, position), "", after
        return self._scalar_value(index, index, position, indent)

    def _scalar_value(self, first: int, index: int, start: int,
                      indent: int) -> Tuple[str, Node, str, int]:
        """Build a scalar value node whose head spans ``first``..``index``."""
        begin = self.starts[index] + start
        raw, end = self._read_scalar(index, start, indent)
        fields = {"raw": raw, "value": _decode_scalar(raw),
                  "style": raw[0] if raw[0] in "\"'" else "plain"}
        row = min(bisect.bisect_right(self.starts, end) - 1, self.count - 1)
        tail = self.text[end:self.starts[row] + len(self.lines[row])]
        head = self.text[self.starts[first]:begin]
        return head, self.builder.node(KIND_SCALAR, fields), tail, row + 1

    def _plain_end(self, start: int) -> int:
        """End offset of one plain-scalar line segment beginning at ``start``."""
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
        """Read one inline scalar at line ``index``, column ``start``."""
        begin = self.starts[index] + start
        if self.text[begin] in "\"'":
            end = _scan_quoted(self.text, begin, index + 1)
            return self.text[begin:end], end
        end = self._plain_end(begin)
        if end == begin:
            raise _syntax("empty scalar value", index + 1)
        while True:
            newline = self.text.find("\n", end)
            if newline < 0 or self.text[end:newline].strip():
                break  # a trailing comment ends the scalar; only spaces may follow
            row = bisect.bisect_right(self.starts, newline)
            if row >= self.count or _is_trivia(self.lines[row]) or _is_marker(self.lines[row]):
                break
            below, line = _indent_of(self.lines[row]), self.lines[row]
            if below < indent or (below == indent and (_starts_item(line, below)
                                                       or _find_colon(line, below) >= 0)):
                break  # a sibling entry, not a continuation of this scalar
            head = self.starts[row] + below
            stop = self._plain_end(head)
            if stop == head:
                break
            end = stop
        return self.text[begin:end], end

    def _read_block_scalar(self, index: int, start: int, indent: int) -> Tuple[str, Node, str, int]:
        """Read a ``|``/``>`` header line plus every body line it owns."""
        line = self.lines[index]
        header = line[start:].rstrip("\r\n").rstrip(" ")
        comment = header.find(" #")
        if comment >= 0:
            header = header[:comment].rstrip(" ")
        if not _BLOCK_RE.fullmatch(header):
            raise _unsupported("BlockScalar", f"unsupported block scalar header {header!r}")
        body: List[str] = []
        cursor = index + 1
        while cursor < self.count and (not self.lines[cursor].strip()
                                       or _indent_of(self.lines[cursor]) > indent):
            body.append(self.lines[cursor])
            cursor += 1
        if not header.endswith("+"):  # trailing blanks are the enclosing block's trivia
            while body and not body[-1].strip():
                body.pop()
                cursor -= 1
        fields = {"raw": "".join(body), "style": header,
                  "value": _decode_block(header, body, indent)}
        return line, self.builder.node(KIND_BLOCK, fields), "", cursor

def _render(node: Node) -> str:
    """Replay a parsed tree's verbatim source text, bottom-up ({p022})."""
    if node.kind in _CONTAINERS:
        return "".join(_render(child) for child in node.children)
    if node.kind in _RAW:
        raw = node.fields.get("raw")
        if not isinstance(raw, str):
            raise _unsupported(str(node.kind), "node carries no verbatim 'raw' text")
        return raw
    if node.kind in _ENTRIES:
        head, tail = node.fields.get("head"), node.fields.get("tail")
        if not isinstance(head, str) or not isinstance(tail, str):
            raise _unsupported(str(node.kind), "entry node carries no verbatim head/tail")
        return head + "".join(_render(child) for child in node.children) + tail
    raise _unsupported(str(node.kind), f"node kind {node.kind!r} has no YAML representation")

def _node_to_plain(node: Node) -> Any:
    """Common model -> plain YAML-compatible dict/list/scalar."""
    if node.kind == KIND_DOCUMENT:
        values = [_node_to_plain(child) for child in node.children if child.kind in _VALUES]
        return (values[0] if len(values) == 1 else values) if values else None
    if node.kind == KIND_MAPPING:
        result: Dict[Any, Any] = {}
        for pair in node.children:
            if pair.kind == KIND_PAIR:
                result[pair.fields.get("key")] = _node_to_plain(pair)
            elif pair.kind not in _TRIVIA:
                raise _unsupported(str(pair.kind), "unexpected child of a YAML mapping")
        return result
    if node.kind == KIND_SEQUENCE:
        return [_node_to_plain(item) for item in node.children if item.kind not in _TRIVIA]
    if node.kind in _ENTRIES:
        return _node_to_plain(node.children[0]) if node.children else None
    if node.kind in (KIND_SCALAR, KIND_BLOCK):
        return node.fields.get("value")
    if node.kind == KIND_TRIVIA:
        return None
    raise _unsupported(str(node.kind), f"node kind {node.kind!r} has no YAML value")

def _emit_scalar(value: Any) -> str:
    """One plain value as canonical YAML scalar text, quoted whenever ambiguous."""
    if isinstance(value, bool) or value is None:
        return "null" if value is None else ("true" if value else "false")
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict) or isinstance(value, (list, tuple)):
        return "{}" if isinstance(value, dict) else "[]"
    if not isinstance(value, str):
        raise _unsupported(type(value).__name__,
                           f"Python type {type(value).__name__!r} has no YAML representation")
    if (not value or value != value.strip() or value[0] in "#&*!?|>%@`{}[],'\"-"
            or ": " in value or value.endswith(":") or "\n" in value
            or _decode_scalar(value) != value):
        return json.dumps(value, ensure_ascii=False)
    return value

def _emit(value: Any, indent: int) -> str:
    """Deterministic canonical YAML for a value with no original source text."""
    pad = "  " * indent
    if isinstance(value, dict) and value:
        return "".join(
            f"{pad}{_emit_scalar(key)}:\n" + _emit(item, indent + 1)
            if isinstance(item, (dict, list, tuple)) and item
            else f"{pad}{_emit_scalar(key)}: {_emit_scalar(item)}\n"
            for key, item in value.items())
    if isinstance(value, (list, tuple)) and value:
        return "".join(
            f"{pad}-\n" + _emit(item, indent + 1) if isinstance(item, (dict, list, tuple)) and item
            else f"{pad}- {_emit_scalar(item)}\n" for item in value)
    return pad + _emit_scalar(value) + "\n"

def _plain_to_node(builder: _NodeBuilder, value: Any, seen: frozenset) -> Node:
    """Plain Python value -> raw-less nodes, rendered canonically by ``_emit``."""
    if isinstance(value, (dict, list, tuple)):
        if id(value) in seen:
            raise _unsupported(type(value).__name__, "circular reference detected")
        deep = seen | {id(value)}
        if isinstance(value, dict):
            return builder.node(KIND_MAPPING, {}, [
                builder.node(KIND_PAIR, {"key": k}, (_plain_to_node(builder, v, deep),))
                for k, v in value.items()])
        return builder.node(KIND_SEQUENCE, {}, [
            builder.node(KIND_ITEM, {}, (_plain_to_node(builder, v, deep),)) for v in value])
    if value is None or isinstance(value, (str, int, float, bool)):
        return builder.node(KIND_SCALAR, {"value": value})
    raise _unsupported(type(value).__name__,
                       f"Python type {type(value).__name__!r} has no YAML representation")

def _is_source_tree(node: Node) -> bool:
    """True when ``node`` came from parsing and can therefore be replayed verbatim."""
    if node.kind == KIND_DOCUMENT:
        return True
    if node.kind in _RAW:
        return isinstance(node.fields.get("raw"), str)
    if node.kind in _ENTRIES:
        return isinstance(node.fields.get("head"), str)
    return any(_is_source_tree(child) for child in node.children)

class YamlFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="yaml"`` plugin (concept C-016)."""

    @property
    def metadata(self) -> FormatPluginMetadata:
        """This plugin's static identity and capability surface."""
        return _METADATA

    def _read(self, source: Union[str, bytes]) -> Tuple[_NodeBuilder, List[Node]]:
        """Decode and read ``source``, raising the module-private syntax signal."""
        if isinstance(source, (bytes, bytearray)):
            try:
                text = bytes(source).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _YamlSyntaxError(f"cannot decode YAML source as utf-8: {exc}") from exc
        elif isinstance(source, str):
            text = source
        else:
            raise _contract_error(f"YAML source must be str or bytes, got {type(source).__name__}")
        builder = _NodeBuilder()
        return builder, _YamlReader(text, builder).read_stream()

    def parse_document(self, source: Union[str, bytes],
                       options: Optional[Mapping[str, Any]] = None, *,
                       source_format_id: Optional[str] = None) -> Document:
        """Parse full YAML source into a ``Document``; damaged input is a parse failure."""
        try:
            builder, children = self._read(source)
        except _YamlSyntaxError as exc:
            raise FormatContentParseFailed(f"cannot parse YAML document: {exc}",
                                           plugin_id=FORMAT_ID) from exc
        return Document(root=builder.node(KIND_DOCUMENT, {}, children), source_format_id=FORMAT_ID)

    def parse_fragment(self, fragment: Union[str, bytes],
                       options: Optional[Mapping[str, Any]] = None, *,
                       source_format_id: Optional[str] = None) -> Node:
        """Parse one YAML fragment into a single ``Node``; damaged text fails per fragment."""
        try:
            builder, children = self._read(fragment)
        except _YamlSyntaxError as exc:
            raise FormatFragmentParseFailed(f"cannot parse YAML fragment: {exc}",
                                            plugin_id=FORMAT_ID) from exc
        return children[0] if len(children) == 1 else builder.node(KIND_DOCUMENT, {}, children)

    def import_external_tree(self, external_tree: Any,
                             options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        """Translate an external YAML representation through the shared importer."""
        return self.import_to_common(external_tree, options)

    def import_to_common(self, external_representation: Any,
                         options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        """The single input translator: YAML source, or an already-decoded plain value."""
        if isinstance(external_representation, (Node, Document)):
            return external_representation
        if isinstance(external_representation, (str, bytes, bytearray)):
            return self.parse_document(external_representation, options)
        return _plain_to_node(_NodeBuilder(), external_representation, frozenset())

    def export_from_common(self, nodes: Union[Node, Document],
                           options: Optional[Mapping[str, Any]] = None) -> Any:
        """Common-model nodes -> plain YAML-compatible dict/list/scalar."""
        root = nodes.root if isinstance(nodes, Document) else nodes
        if not isinstance(root, Node):
            raise _contract_error(f"expected a Node or Document, got {type(nodes).__name__}")
        return _node_to_plain(root)

    def generate_output(self, target: Union[Node, Document, Any],
                        options: Optional[Mapping[str, Any]] = None) -> Union[str, bytes]:
        """Final YAML text (bytes with ``options['as_bytes']``): verbatim, else canonical."""
        options = options or {}
        if isinstance(target, (Node, Document)):
            root = target.root if isinstance(target, Document) else target
            text = _render(root) if _is_source_tree(root) else _emit(_node_to_plain(root), 0)
        elif isinstance(target, (dict, list, tuple, str, int, float, bool)) or target is None:
            text = _emit(target, 0)
        else:
            raise _contract_error(f"cannot generate output for {type(target).__name__}")
        return text.encode("utf-8") if options.get("as_bytes") else text

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """YAML models none of function/method/class/module; empty is correct ({p056})."""
        return _ROLE_MAP

    def render_document(self, document: Document) -> bytes:
        """``FormatBoundary``: render a whole ``Document`` back to source bytes."""
        result = self.generate_output(document, {"as_bytes": True})
        if not isinstance(result, bytes):
            raise _contract_error(f"render_document expected bytes, got {type(result).__name__}")
        return result

    def render_fragment(self, node: Node) -> str:
        """``FormatBoundary``: render a single fragment ``Node`` back to source text."""
        result = self.generate_output(node, {})
        if not isinstance(result, str):
            raise _contract_error(f"render_fragment expected str, got {type(result).__name__}")
        return result

# Stateless singleton the sibling registry step imports and registers under
# ``format_id="yaml"`` for the ``.yaml``/``.yml`` extensions.
YAML_FORMAT_PLUGIN = YamlFormatPlugin()
