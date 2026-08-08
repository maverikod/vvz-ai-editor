"""The TOML format plugin (concept C-016, atomic step A-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``FormatPluginContract``/``FormatBoundary`` for ``format_id="toml"``. A document
is an ordered tree of ``toml:Document`` -> ``toml:Table``/``toml:ArrayOfTables``
-> ``toml:KeyValue``/``toml:Comment``/``toml:Blank``. Headers nest by dotted-key
prefix, so ``[a.b]`` becomes a child of ``[a]`` while a repeated ``[[a]]`` stays a
sibling: array-of-tables semantics carried structurally, not by re-reading text.

Byte fidelity ({p022}): ``tomllib`` only decides whether a document is *valid* --
it drops comments, blank lines, quoting and spacing, so it can never drive
rendering. A lossless scanner instead cuts the source into entries whose spans
tile it with no gap and no overlap; each node stores its span in ``fields["raw"]``
and rendering concatenates those spans depth-first, which is document order by
construction -- hence ``render_document(parse_document(raw)) == raw``. Valid TOML
the scanner cannot tile raises ``UNSUPPORTED_TRANSLATION``, never a silent
reformat. ``_Entry``/``_ParsedSource`` stay private. Every node gets a fresh UUID4
``node_id`` and a local ``short_id`` ({p013}). Errors: bad document/fragment ->
``FormatContent``/``FormatFragmentParseFailed``; unrepresentable ->
``UnsupportedTranslation``; ``FormatPluginContractError`` only for a caller
breaking the call contract. Labels: {p013} {p022} {p049} {p056} {p057}.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.core.short_id import ShortIdMap
from tree_engine.exceptions import (FormatContentParseFailed, FormatFragmentParseFailed,
                                    FormatPluginContractError, UnsupportedTranslation)
from tree_engine.plugins.contract import (FormatPluginContract, FormatPluginMetadata,
                                          SemanticRoleMapping)
from tree_engine.plugins.json_pointer import JsonPointerNotation

__all__ = ["FORMAT_ID", "TOML_POINTER", "TomlFormatPlugin", "TOML_FORMAT_PLUGIN"]

FORMAT_ID = "toml"
KIND_DOCUMENT = f"{FORMAT_ID}:Document"
KIND_TABLE = f"{FORMAT_ID}:Table"
KIND_ARRAY_OF_TABLES = f"{FORMAT_ID}:ArrayOfTables"
KIND_KEYVALUE = f"{FORMAT_ID}:KeyValue"
KIND_COMMENT = f"{FORMAT_ID}:Comment"
KIND_BLANK = f"{FORMAT_ID}:Blank"

# ``aliases`` is empty (TOML has no second established name; the registry still
# indexes format_id + ``.toml``), and so is the role map: TOML has no
# function/method/class/module, so ``roles_for(role) == ()`` ({p056}).
_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID, aliases=(), file_extensions=("toml",),
    plugin_version="1.0.0", contract_version="1.0.0",
    capabilities={"semantic_role_mapping": True, "byte_identical_round_trip": True})
_ROLE_MAP = SemanticRoleMapping({})
_HEADER_KINDS = (KIND_TABLE, KIND_ARRAY_OF_TABLES)
_LEAF_KINDS = (KIND_KEYVALUE, KIND_COMMENT, KIND_BLANK)
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_VALUE_STOP = "\n#,]}"
_Options = Optional[Mapping[str, Any]]
_Source = Union[str, bytes]
def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(message, plugin_id=FORMAT_ID)
def _unsupported(node_type: str, message: str) -> UnsupportedTranslation:
    return UnsupportedTranslation(message, node_type=node_type, format_id=FORMAT_ID)
class _TomlScanError(Exception):
    """Internal, module-private lossless-scan signal (never escapes)."""
@dataclass(frozen=True)
class _Entry:
    """One tiled source span plus what the scanner learned about it."""
    kind: str
    raw: str
    key: str = ""
    value_text: str = ""
@dataclass(frozen=True)
class _ParsedSource:
    """A whole scanned document: the private marker type ``import_to_common``
    dispatches on, holding the entries whose spans tile the source exactly."""
    entries: Tuple[_Entry, ...]

def _scan_string(text: str, pos: int) -> int:
    """Scan one TOML string literal starting at its opening quote."""
    quote = text[pos]
    multiline = text[pos : pos + 3] == quote * 3
    index = pos + 3 if multiline else pos + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and quote == '"':
            index += 2
            continue
        if char == quote:
            if not multiline:
                return index + 1
            if text[index : index + 3] == quote * 3:
                # A run longer than three ends with the closing delimiter; the
                # leading extras are content (`"""a""""` holds one quote).
                run = index
                while run < len(text) and text[run] == quote:
                    run += 1
                return run
        elif char == "\n" and not multiline:
            break
        index += 1
    raise _TomlScanError(f"unterminated string opened at offset {pos}")
def _skip_atom(text: str, index: int) -> int:
    """Advance one position, jumping a whole string literal or comment."""
    if text[index] in "\"'":
        return _scan_string(text, index)
    if text[index] == "#":
        newline = text.find("\n", index)
        return len(text) if newline == -1 else newline
    return index + 1
def _scan_bracketed(text: str, pos: int) -> int:
    """Scan a ``[...]``/``{...}`` span, nesting- and quote-aware."""
    depth = 0
    index = pos
    while index < len(text):
        if text[index] in "[{":
            depth += 1
        elif text[index] in "]}":
            depth -= 1
            if depth == 0:
                return index + 1
        index = _skip_atom(text, index)
    raise _TomlScanError(f"unterminated bracket opened at offset {pos}")
def _scan_value(text: str, pos: int) -> int:
    """Scan one right-hand-side value, excluding any trailing comment."""
    if text[pos] in "\"'":
        return _scan_string(text, pos)
    if text[pos] in "[{":
        return _scan_bracketed(text, pos)
    index = pos
    while index < len(text) and text[index] not in _VALUE_STOP:
        index += 1
    while index > pos and text[index - 1] in " \t\r":
        index -= 1
    if index == pos:
        raise _TomlScanError(f"missing value at offset {pos}")
    return index
def _scan_line_tail(text: str, pos: int) -> int:
    """Consume trailing blanks, an optional comment, and the line break."""
    index = pos
    while index < len(text) and text[index] in " \t\r":
        index += 1
    if index < len(text) and text[index] == "#":
        index = _skip_atom(text, index)
    return index + 1 if index < len(text) and text[index] == "\n" else index
def _scan_key(text: str, pos: int) -> int:
    """Scan a possibly dotted and quoted key up to its ``=`` separator."""
    index = pos
    while index < len(text) and text[index] != "\n":
        if text[index] == "=":
            return index
        index = _skip_atom(text, index)
    raise _TomlScanError(f"expected '=' after the key at offset {pos}")
def _scan_entries(text: str) -> Tuple[_Entry, ...]:
    """Split ``text`` into entries whose spans tile it exactly."""
    entries: List[_Entry] = []
    pos, size = 0, len(text)
    while pos < size:
        start = index = pos
        while index < size and text[index] in " \t\r":
            index += 1
        if index >= size or text[index] == "\n":
            pos = index + 1 if index < size else size
            entries.append(_Entry(KIND_BLANK, text[start:pos]))
        elif text[index] == "#":
            pos = _scan_line_tail(text, index)
            entries.append(_Entry(KIND_COMMENT, text[start:pos], value_text=text[index:pos].rstrip("\r\n")))
        elif text[index] == "[":
            width = 2 if text[index : index + 2] == "[[" else 1
            close = _scan_bracketed(text, index)
            key = text[index + width : close - width].strip()
            if not key:
                raise _TomlScanError(f"empty table header at offset {index}")
            pos = _scan_line_tail(text, close)
            kind = KIND_ARRAY_OF_TABLES if width == 2 else KIND_TABLE
            entries.append(_Entry(kind, text[start:pos], key=key))
        else:
            separator = _scan_key(text, index)
            value_start = separator + 1
            while value_start < size and text[value_start] in " \t":
                value_start += 1
            if value_start >= size:
                raise _TomlScanError(f"missing value after '=' at offset {separator}")
            value_end = _scan_value(text, value_start)
            pos = _scan_line_tail(text, value_end)
            entries.append(_Entry(KIND_KEYVALUE, text[start:pos], key=text[index:separator].strip(),
                                  value_text=text[value_start:value_end]))
    return tuple(entries)

def _new_node(kind: str, fields: Mapping[str, Any], kids: Sequence[Node], ids: ShortIdMap) -> Node:
    """Build a validated node carrying a fresh UUID4 id and short_id ({p013})."""
    validated = make_node(kind, fields=dict(fields), children=tuple(kids))
    node_id = generate_node_id()
    return replace(validated, node_id=node_id, short_id=ids.allocate(node_id))
def _build_root(source: _ParsedSource, ids: ShortIdMap) -> Node:
    """Nest the tiled entries into a tree; table headers nest by key prefix."""
    top: List[Node] = []
    stack: List[Tuple[str, _Entry, List[Node]]] = []

    def close_one() -> None:
        key, entry, children = stack.pop()
        node = _new_node(entry.kind, {"raw": entry.raw, "key": key}, children, ids)
        (stack[-1][2] if stack else top).append(node)

    def leaf(entry: _Entry) -> Node:
        """One non-header entry -> a leaf node keeping its exact span."""
        fields: dict = {"raw": entry.raw}
        if entry.kind == KIND_KEYVALUE:
            fields["key"], fields["value_text"] = entry.key, entry.value_text
        elif entry.kind == KIND_COMMENT:
            fields["text"] = entry.value_text
        return _new_node(entry.kind, fields, (), ids)

    for entry in source.entries:
        if entry.kind in _HEADER_KINDS:
            while stack and not entry.key.startswith(stack[-1][0] + "."):
                close_one()
            stack.append((entry.key, entry, []))
        else:
            (stack[-1][2] if stack else top).append(leaf(entry))
    while stack:
        close_one()
    return _new_node(KIND_DOCUMENT, {}, top, ids)
def _render(node: Node) -> str:
    """Common model -> text, replaying each node's exact stored span. A node with
    no span (caller-synthesized) falls back to a minimal deterministic form."""
    kind, raw = node.kind, node.fields.get("raw")
    if kind == KIND_DOCUMENT:
        return "".join(_render(child) for child in node.children)
    if kind in _HEADER_KINDS:
        if not isinstance(raw, str):
            brackets = "[[{}]]" if kind == KIND_ARRAY_OF_TABLES else "[{}]"
            raw = brackets.format(node.fields.get("key", "")) + "\n"
        return raw + "".join(_render(child) for child in node.children)
    if kind in _LEAF_KINDS:
        if isinstance(raw, str):
            return raw
        if kind == KIND_KEYVALUE:
            return f"{node.fields.get('key', '')} = {node.fields.get('value_text', '')}\n"
        return f"{node.fields.get('text', '#')}\n" if kind == KIND_COMMENT else "\n"
    raise _unsupported(str(kind), f"node kind {kind!r} has no TOML representation")

def _dump_key(key: Any) -> str:
    """Render one key segment, quoting it when it is not a bare TOML key."""
    if not isinstance(key, str):
        raise _unsupported(type(key).__name__, f"TOML keys must be strings, got {key!r}")
    return key if _BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)
def _dump_value(value: Any) -> str:
    """Render one inline TOML value; an unmappable type raises ({p049})."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value) if isinstance(value, int) else repr(value)
    if isinstance(value, str):
        # TOML basic strings accept exactly the JSON escape set minus "\/",
        # which json.dumps never emits, so its output is a valid literal.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_dump_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{_dump_key(k)} = {_dump_value(v)}" for k, v in value.items()) + "}"
    raise _unsupported(type(value).__name__, f"{type(value).__name__!r} has no TOML value form")
def _dump_toml(mapping: Any, path: Tuple[str, ...] = ()) -> str:
    """Plain mapping -> TOML: scalars first, then sub-tables; a non-empty list of
    mappings becomes a ``[[array of tables]]``."""
    if not isinstance(mapping, Mapping):
        raise _unsupported(type(mapping).__name__, "a TOML document root must be a mapping")
    pairs: List[str] = []
    tables: List[str] = []
    for key, value in mapping.items():
        child = path + (key,)
        head = ".".join(_dump_key(part) for part in child)
        if isinstance(value, Mapping):
            tables.append(f"[{head}]\n" + _dump_toml(value, child))
        elif (isinstance(value, (list, tuple)) and len(value) > 0
                and all(isinstance(item, Mapping) for item in value)):
            tables.extend(f"[[{head}]]\n" + _dump_toml(item, child) for item in value)
        else:
            pairs.append(f"{_dump_key(key)} = {_dump_value(value)}\n")
    return "".join(pairs) + "".join(tables)

def _split_dotted_key(key: str) -> Tuple[str, ...]:
    """Split a TOML dotted key into its segments, unquoting each one.

    ``a.b`` is two segments, and so is ``a."b.c"`` -- but the second one's dot
    is content, not a separator, which is exactly why this cannot be a
    ``str.split(".")``. Quoted segments are decoded so the resulting token is
    the key a reader means, not the source spelling of it.
    """

    segments: List[str] = []
    current: List[str] = []
    index = 0
    while index < len(key):
        char = key[index]
        if char in "\"'":
            try:
                end = _scan_string(key, index)
            except _TomlScanError:
                # A key no scanner can close is not a key this notation can
                # express; the caller-synthesized node it came from simply gets
                # no pointer rather than one built from a guess at where the
                # quote was meant to end.
                return ()
            literal = key[index:end]
            try:
                current.append(json.loads(literal) if char == '"' else literal[1:-1])
            except ValueError:
                current.append(literal)
            index = end
            continue
        if char == ".":
            segments.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    segments.append("".join(current).strip())
    return tuple(segment for segment in segments if segment != "")


def _key_text(node: Node) -> str:
    """A node's header/key text, or ``""`` when it carries none as a string.

    ``toml:Document`` has no key at all, and a caller-synthesized node may hold
    a non-string one; both answer ``""``, which
    :func:`_split_dotted_key` turns into no segments and hence no pointer.
    """

    key = node.fields.get("key")
    return key if isinstance(key, str) else ""


def _relative_key(parent: Node, child: Node) -> Tuple[str, ...]:
    """The header segments ``child`` adds below ``parent``'s own header.

    A table header carries its FULL dotted key -- ``[a.b]`` stores ``"a.b"``
    even though the tree already nests it under ``[a]`` -- so emitting all of
    it would produce ``/a/a/b``. The parent's own segments are dropped, which
    is a prefix comparison on parsed segments rather than on raw text, so a
    quoted segment cannot be mis-stripped.
    """

    child_segments = _split_dotted_key(_key_text(child))
    parent_segments = _split_dotted_key(_key_text(parent))
    if parent_segments and child_segments[:len(parent_segments)] == parent_segments:
        return child_segments[len(parent_segments):]
    return child_segments


def _array_of_tables_ordinal(parent: Node, child: Node) -> int:
    """How many earlier siblings repeat ``child``'s ``[[header]]``.

    ``[[a]]`` written three times is a three-element array, kept structurally
    as three sibling nodes with one key; their pointers differ only by this
    index, so it has to be counted over the siblings rather than read off the
    node.
    """

    key = child.fields.get("key")
    count = 0
    for sibling in parent.children:
        if sibling is child:
            break
        if sibling.kind == KIND_ARRAY_OF_TABLES and sibling.fields.get("key") == key:
            count += 1
    return count


def _pointer_step(parent: Node, child: Node, ordinal: int) -> Optional[Tuple[Tuple[str, ...], bool]]:
    """This format's structural half of RFC 6901, for ``JsonPointerNotation``.

    TOML is a line-tiled model rather than a value tree, so the mapping is the
    least direct of the three: a table's pointer is its dotted key expanded
    into one token per segment, a key/value pair's is the same below whatever
    table contains it, and a repeated ``[[table]]`` adds its occurrence index
    because that is what the array element's pointer is. Comments and blank
    lines exist only to make the document render byte-identically; they are
    not values and get no pointer.
    """

    kind = child.kind
    if kind == KIND_KEYVALUE:
        segments = _split_dotted_key(_key_text(child))
        return (segments, True) if segments else None
    if kind == KIND_TABLE:
        segments = _relative_key(parent, child)
        return (segments, True) if segments else None
    if kind == KIND_ARRAY_OF_TABLES:
        segments = _relative_key(parent, child)
        if not segments:
            return None
        return (segments + (str(_array_of_tables_ordinal(parent, child)),), True)
    return None


#: The plugin's reference-notation declaration, read duck-typed by
#: ``tree_engine.core.identifier_map``. A TOML document IS its root table, so
#: ``toml:Document`` is what the empty pointer names.
TOML_POINTER = JsonPointerNotation(_pointer_step, root_addressable=True)


class TomlFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="toml"`` plugin (concept C-016)."""

    #: This format's native reference notation ({p021} third correspondence):
    #: JSON Pointer, computed and parsed here rather than by shared code.
    native_reference = TOML_POINTER

    @property
    def metadata(self) -> FormatPluginMetadata:
        """Static identity: ``toml`` plus the ``.toml`` file extension."""
        return _METADATA

    def _scan(self, text: str, malformed: type) -> _ParsedSource:
        """Validate with ``tomllib``, then tile the text losslessly."""
        try:
            tomllib.loads(text)  # the authority on validity, never on layout
            entries = _scan_entries(text)
        except (tomllib.TOMLDecodeError, ValueError, TypeError, _TomlScanError) as exc:
            raise malformed(f"cannot parse TOML: {exc}", format_id=FORMAT_ID) from exc
        if "".join(entry.raw for entry in entries) != text:
            raise _unsupported(KIND_DOCUMENT, "this TOML cannot be tiled losslessly")
        return _ParsedSource(entries=entries)

    @staticmethod
    def _decode(source: _Source, label: str) -> str:
        """Accept text or UTF-8 bytes; anything else breaks the call contract."""
        if isinstance(source, str):
            return source
        if isinstance(source, (bytes, bytearray)):
            return bytes(source).decode("utf-8")
        raise _contract_error(f"{label} must be str or bytes, got {type(source).__name__}")

    def parse_document(self, source: _Source, options: _Options = None, *, source_format_id: Optional[str] = None) -> Document:
        """Parse a whole TOML document ({p022}); malformed input raises
        ``FormatContentParseFailed`` (FORMAT_CONTENT_PARSE_FAILED)."""
        text = self._decode(source, "source")
        result = self.import_to_common(self._scan(text, FormatContentParseFailed), options)
        if not isinstance(result, Document):
            raise _contract_error(f"a document must yield a Document, got {type(result).__name__}")
        return result

    def parse_fragment(self, fragment: _Source, options: _Options = None, *, source_format_id: Optional[str] = None) -> Node:
        """Parse a standalone TOML fragment into one container ``Node``; an
        unrecognizable one raises ``FormatFragmentParseFailed``. The raw text is
        never returned as a "no structure" signal: the boundary fixes ``Node``."""
        text = self._decode(fragment, "fragment")
        return _build_root(self._scan(text, FormatFragmentParseFailed), ShortIdMap())

    def import_external_tree(self, external_tree: Any, options: _Options = None) -> Union[Node, Document]:
        """Import an already-decoded TOML mapping (e.g. from ``tomllib.load``)."""
        return self.import_to_common(external_tree, options)

    def import_to_common(self, external_representation: Any, options: _Options = None) -> Union[Node, Document]:
        """The single input translator ({p056}, {p057}): this module's private scan
        result, or a plain mapping -- serialized to TOML then re-scanned, so it
        carries the same span invariants as a parse."""
        if isinstance(external_representation, _ParsedSource):
            root = _build_root(external_representation, ShortIdMap())
            return Document(root=root, source_format_id=FORMAT_ID)
        if isinstance(external_representation, Mapping):
            return self.parse_document(_dump_toml(external_representation), options)
        raise _unsupported(type(external_representation).__name__, "expected a scan or mapping")

    def export_from_common(self, nodes: Union[Node, Document], options: _Options = None) -> Any:
        """Common-model nodes -> the plain mapping backend representation. Native
        date/time literals surface here as ``datetime``/``date``/``time``; in the
        tree they stay exact text, which is what keeps rendering byte-identical."""
        if not isinstance(nodes, (Node, Document)):
            raise _contract_error(f"expected a Node or Document, got {type(nodes).__name__}")
        root = nodes.root if isinstance(nodes, Document) else nodes
        try:
            return tomllib.loads(_render(root))
        except (tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
            raise _unsupported(str(root.kind), f"not a standalone TOML document: {exc}") from exc

    def generate_output(self, target: Union[Node, Document, Any], options: _Options = None) -> Union[str, bytes]:
        """Final TOML text (bytes with ``options["as_bytes"]``): common-model input
        replays stored spans byte-identically, a plain mapping dumps canonically."""
        options = options or {}
        if isinstance(target, (Node, Document)):
            text = _render(target.root if isinstance(target, Document) else target)
        elif isinstance(target, Mapping):
            text = _dump_toml(target)
        elif isinstance(target, str):
            text = target
        else:
            raise _contract_error(f"cannot render {type(target).__name__}; expected Node/Document/mapping/str")
        return text.encode("utf-8") if options.get("as_bytes") else text

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """TOML models no function, method, class, or module ({p056})."""
        return _ROLE_MAP

    def render_document(self, document: Document) -> bytes:
        """CORE-facing counterpart of ``parse_document``: exact UTF-8 bytes."""
        result = self.generate_output(document, {"as_bytes": True})
        if not isinstance(result, bytes):
            raise _contract_error(f"render_document expected bytes, got {type(result).__name__}")
        return result

    def render_fragment(self, node: Node) -> str:
        """CORE-facing counterpart of ``parse_fragment``: exact source text."""
        result = self.generate_output(node, {})
        if not isinstance(result, str):
            raise _contract_error(f"render_fragment expected str, got {type(result).__name__}")
        return result

# Ready-made singleton a sibling registry step can import and register under
# ``format_id="toml"``, mirroring ``JSON_FORMAT_PLUGIN``/``BSL_FORMAT_PLUGIN``.
TOML_FORMAT_PLUGIN = TomlFormatPlugin()
