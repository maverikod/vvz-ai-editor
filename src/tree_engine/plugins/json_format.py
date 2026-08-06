"""The JSON format plugin (concept C-016, atomic step A-003).

Implements ``FormatPluginContract`` and ``FormatBoundary`` for
``format_id="json"``. Objects map to keyed container nodes (``json:Object``,
whose children are ``json:Member`` nodes carrying the member's key), arrays
to ordered containers (``json:Array``), scalars to leaf nodes
(``json:String``/``Number``/``Boolean``/``Null``). No external parser object
escapes this module: the private parser shapes (``_RawValue``/
``_DocumentSource``) always convert to common-model ``Node``/``Document``.

Byte fidelity: every node built from parsed text keeps its exact original
source slice in ``fields["raw"]``. A JSON value's span is lexically
self-contained, so replaying a stored ``"raw"`` string reproduces the whole
subtree verbatim; nothing untouched since parsing is ever re-formatted. The
document root's ``"raw"`` is widened to the *entire* original text so outer
leading/trailing whitespace round-trips too. A node built without parsing
(``import_to_common`` on a plain Python value) carries no ``"raw"`` and
falls back to deterministic canonical rendering, computed bottom-up so
untouched raw-carrying descendants still reuse their exact original text.

Source-of-truth requirement labels honored here: {p026}, {p060}, {p062}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import (
    FormatPluginContract,
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRoleMapping,
    UnsupportedTranslationError,
)

__all__ = ["FORMAT_ID", "JsonFormatPlugin", "JSON_FORMAT_PLUGIN"]

FORMAT_ID = "json"
KIND_OBJECT = f"{FORMAT_ID}:Object"
KIND_MEMBER = f"{FORMAT_ID}:Member"
KIND_ARRAY = f"{FORMAT_ID}:Array"
KIND_STRING = f"{FORMAT_ID}:String"
KIND_NUMBER = f"{FORMAT_ID}:Number"
KIND_BOOLEAN = f"{FORMAT_ID}:Boolean"
KIND_NULL = f"{FORMAT_ID}:Null"

_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID,
    aliases=(),
    file_extensions=("json",),
    plugin_version="1.0.0",
    contract_version="1.0.0",
    capabilities={"semantic_role_mapping": True, "byte_identical_round_trip": True},
)

# JSON models no function/method/class/module; empty is correct, not an error.
_ROLE_MAP = SemanticRoleMapping({})
_WHITESPACE = " \t\n\r"

def _contract_error(message: str) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, message=message)

def _unsupported(node_type: str, message: str) -> UnsupportedTranslationError:
    return UnsupportedTranslationError(node_type=node_type, format_id=FORMAT_ID, message=message)

class _JsonParseError(Exception):
    """Internal, module-private malformed-JSON signal (never escapes)."""

@dataclass
class _RawValue:
    """One parsed JSON value plus its raw slice; private, never returned."""
    kind: str
    raw: str
    value: Any = None
    members: List[Tuple[str, "_RawValue"]] = field(default_factory=list)
    items: List["_RawValue"] = field(default_factory=list)

@dataclass
class _DocumentSource:
    """A whole parsed document: its top-level value plus the full text."""
    value: _RawValue
    full_text: str

_SCALAR_DECODER = json.JSONDecoder()

def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in _WHITESPACE:
        pos += 1
    return pos

def _scan_value(text: str, pos: int) -> Tuple[_RawValue, int]:
    pos = _skip_ws(text, pos)
    if pos >= len(text):
        raise _JsonParseError(f"unexpected end of input at position {pos}")
    char = text[pos]
    if char == "{":
        return _scan_object(text, pos)
    if char == "[":
        return _scan_array(text, pos)
    try:
        value, end = _SCALAR_DECODER.raw_decode(text, pos)
    except json.JSONDecodeError as exc:
        raise _JsonParseError(f"malformed JSON at position {pos}: {exc}") from exc
    if isinstance(value, (dict, list)):
        raise _JsonParseError(f"unexpected container at position {pos}")
    if isinstance(value, bool):
        kind = KIND_BOOLEAN
    elif value is None:
        kind = KIND_NULL
    elif isinstance(value, str):
        kind = KIND_STRING
    elif isinstance(value, (int, float)):
        kind = KIND_NUMBER
    else:  # pragma: no cover - stdlib json never produces another type
        raise _JsonParseError(f"unsupported scalar type at position {pos}")
    return _RawValue(kind=kind, raw=text[pos:end], value=value), end

def _scan_object(text: str, pos: int) -> Tuple[_RawValue, int]:
    start = pos
    pos += 1
    members: List[Tuple[str, _RawValue]] = []
    pos = _skip_ws(text, pos)
    if pos < len(text) and text[pos] == "}":
        pos += 1
        return _RawValue(kind=KIND_OBJECT, raw=text[start:pos], members=members), pos
    while True:
        pos = _skip_ws(text, pos)
        if pos >= len(text) or text[pos] != '"':
            raise _JsonParseError(f"expected object key (string) at position {pos}")
        try:
            key, pos = _SCALAR_DECODER.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            raise _JsonParseError(f"malformed object key at position {pos}: {exc}") from exc
        pos = _skip_ws(text, pos)
        if pos >= len(text) or text[pos] != ":":
            raise _JsonParseError(f"expected ':' at position {pos}")
        value_raw, pos = _scan_value(text, pos + 1)
        members.append((key, value_raw))
        pos = _skip_ws(text, pos)
        if pos >= len(text):
            raise _JsonParseError("unterminated object")
        if text[pos] == ",":
            pos += 1
            continue
        if text[pos] == "}":
            pos += 1
            break
        raise _JsonParseError(f"expected ',' or '}}' at position {pos}")
    return _RawValue(kind=KIND_OBJECT, raw=text[start:pos], members=members), pos

def _scan_array(text: str, pos: int) -> Tuple[_RawValue, int]:
    start = pos
    pos += 1
    items: List[_RawValue] = []
    pos = _skip_ws(text, pos)
    if pos < len(text) and text[pos] == "]":
        pos += 1
        return _RawValue(kind=KIND_ARRAY, raw=text[start:pos], items=items), pos
    while True:
        item_raw, pos = _scan_value(text, pos)
        items.append(item_raw)
        pos = _skip_ws(text, pos)
        if pos >= len(text):
            raise _JsonParseError("unterminated array")
        if text[pos] == ",":
            pos += 1
            continue
        if text[pos] == "]":
            pos += 1
            break
        raise _JsonParseError(f"expected ',' or ']' at position {pos}")
    return _RawValue(kind=KIND_ARRAY, raw=text[start:pos], items=items), pos

def _parse_json_text(text: str) -> _RawValue:
    """Parse one whole document; raises ``_JsonParseError`` on anything
    malformed, including trailing non-whitespace garbage."""
    value, end = _scan_value(text, 0)
    if text[end:].strip(_WHITESPACE):
        raise _JsonParseError(f"unexpected trailing content at position {end}")
    return value

def _raw_to_node(raw_value: _RawValue) -> Node:
    if raw_value.kind == KIND_OBJECT:
        members = tuple(
            make_node(KIND_MEMBER, fields={"key": key}, children=(_raw_to_node(value),))
            for key, value in raw_value.members
        )
        return make_node(KIND_OBJECT, fields={"raw": raw_value.raw}, children=members)
    if raw_value.kind == KIND_ARRAY:
        items = tuple(_raw_to_node(item) for item in raw_value.items)
        return make_node(KIND_ARRAY, fields={"raw": raw_value.raw}, children=items)
    if raw_value.kind == KIND_NULL:
        return make_node(KIND_NULL, fields={"raw": raw_value.raw})
    return make_node(raw_value.kind, fields={"value": raw_value.value, "raw": raw_value.raw})

def _plain_to_node(value: Any, ancestors: frozenset) -> Node:
    """Build a raw-less node tree from an already-decoded plain Python
    value; ``ancestors`` holds container ``id()``s on the recursion path,
    rejecting a circular structure instead of looping forever."""
    if isinstance(value, dict):
        marker = id(value)
        if marker in ancestors:
            raise _unsupported("object", "circular reference detected")
        nested = ancestors | {marker}
        members = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise _unsupported("object-key", f"non-string object key: {key!r}")
            members.append(
                make_node(KIND_MEMBER, fields={"key": key}, children=(_plain_to_node(item, nested),))
            )
        return make_node(KIND_OBJECT, fields={}, children=tuple(members))
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in ancestors:
            raise _unsupported("array", "circular reference detected")
        nested = ancestors | {marker}
        return make_node(KIND_ARRAY, fields={}, children=tuple(_plain_to_node(v, nested) for v in value))
    if isinstance(value, bool):
        return make_node(KIND_BOOLEAN, fields={"value": value})
    if isinstance(value, str):
        return make_node(KIND_STRING, fields={"value": value})
    if isinstance(value, (int, float)):
        return make_node(KIND_NUMBER, fields={"value": value})
    if value is None:
        return make_node(KIND_NULL, fields={})
    raise _unsupported(
        type(value).__name__, f"Python type {type(value).__name__!r} has no JSON representation"
    )

def _node_to_plain(node: Node, ancestors: frozenset) -> Any:
    """Common model -> JSON-compatible plain dict/list/scalar."""
    marker = id(node)
    if marker in ancestors:
        raise _unsupported(str(node.kind), "circular reference detected")
    nested = ancestors | {marker}
    kind = node.kind
    if kind == KIND_OBJECT:
        result: Dict[str, Any] = {}
        for member in node.children:
            if member.kind != KIND_MEMBER or not member.children:
                raise _unsupported(str(member.kind), "malformed object member")
            key = member.fields.get("key")
            if not isinstance(key, str):
                raise _unsupported("Member", "member key must be a string")
            result[key] = _node_to_plain(member.children[0], nested)
        return result
    if kind == KIND_ARRAY:
        return [_node_to_plain(child, nested) for child in node.children]
    if kind == KIND_STRING:
        value = node.fields.get("value")
        if not isinstance(value, str):
            raise _unsupported(str(kind), "String node missing a str value")
        return value
    if kind == KIND_NUMBER:
        value = node.fields.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _unsupported(str(kind), "Number node missing a numeric value")
        return value
    if kind == KIND_BOOLEAN:
        value = node.fields.get("value")
        if not isinstance(value, bool):
            raise _unsupported(str(kind), "Boolean node missing a bool value")
        return value
    if kind == KIND_NULL:
        return None
    raise _unsupported(str(kind), f"node kind {kind!r} has no JSON representation")

def _render_node(node: Node) -> str:
    """Common model -> final text, reusing stored raw text where present."""
    raw = node.fields.get("raw") if isinstance(node.fields, Mapping) else None
    if isinstance(raw, str):
        return raw
    kind = node.kind
    if kind == KIND_OBJECT:
        parts = []
        for member in node.children:
            key = member.fields.get("key", "")
            value_text = _render_node(member.children[0]) if member.children else "null"
            parts.append(f"{json.dumps(key, ensure_ascii=False)}: {value_text}")
        return "{" + ", ".join(parts) + "}"
    if kind == KIND_ARRAY:
        return "[" + ", ".join(_render_node(child) for child in node.children) + "]"
    if kind == KIND_STRING:
        return json.dumps(node.fields.get("value"), ensure_ascii=False)
    if kind == KIND_NUMBER:
        return json.dumps(node.fields.get("value"))
    if kind == KIND_BOOLEAN:
        return "true" if node.fields.get("value") else "false"
    if kind == KIND_NULL:
        return "null"
    raise _contract_error(f"cannot render node kind {kind!r} to JSON")

class JsonFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="json"`` plugin (concept C-016)."""

    @property
    def metadata(self) -> FormatPluginMetadata:
        return _METADATA

    def parse_document(
        self, source: Union[str, bytes], options: Optional[Mapping[str, Any]] = None,
        *, source_format_id: Optional[str] = None,
    ) -> Document:
        """Parse full JSON source into a ``Document``; raises
        ``FORMAT_CONTENT_PARSE_FAILED`` on malformed JSON."""
        text = source.decode("utf-8") if isinstance(source, bytes) else source
        try:
            value = _parse_json_text(text)
        except _JsonParseError as exc:
            raise FormatPluginContractError(
                plugin_id=FORMAT_ID,
                error_code=ErrorCode.FORMAT_CONTENT_PARSE_FAILED,
                message=f"cannot parse JSON document: {exc}",
            ) from exc
        result = self.import_to_common(_DocumentSource(value=value, full_text=text), options)
        if not isinstance(result, Document):
            raise _contract_error(f"parsing a document must yield a Document, got {type(result).__name__}")
        return result

    def import_external_tree(self, external_tree: Any, options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        return self.import_to_common(external_tree, options)

    def parse_fragment(
        self, fragment: Union[str, bytes], options: Optional[Mapping[str, Any]] = None,
        *, source_format_id: Optional[str] = None,
    ) -> Union[Node, str]:
        """Parse a single JSON value fragment; returns the fragment's own
        text (never raising) when it is not a recognizable JSON value."""
        text = fragment.decode("utf-8") if isinstance(fragment, bytes) else fragment
        try:
            value = _parse_json_text(text)
        except _JsonParseError:
            return text
        result = self.import_to_common(value, options)
        if not isinstance(result, Node):
            raise _contract_error(f"parsing a fragment must yield a Node, got {type(result).__name__}")
        return result

    def import_to_common(self, external_representation: Any, options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        """Shared input translator: accepts this module's private parser
        shapes, or an already-decoded plain Python JSON value."""
        if isinstance(external_representation, _DocumentSource):
            root = _raw_to_node(external_representation.value)
            widened = dict(root.fields)
            widened["raw"] = external_representation.full_text
            root = make_node(root.kind, fields=widened, children=root.children)
            return Document(root=root, source_format_id=FORMAT_ID)
        if isinstance(external_representation, _RawValue):
            return _raw_to_node(external_representation)
        return _plain_to_node(external_representation, frozenset())

    def export_from_common(self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None) -> Any:
        """Common-model nodes -> JSON-compatible dict/list/scalar; raises
        ``UnsupportedTranslationError`` for an unmappable construct."""
        root = nodes.root if isinstance(nodes, Document) else nodes
        if not isinstance(root, Node):
            raise _contract_error(f"expected a Node or Document, got {type(nodes).__name__}")
        return _node_to_plain(root, frozenset())

    def generate_output(self, target: Union[Node, Document, Any], options: Optional[Mapping[str, Any]] = None) -> Union[str, bytes]:
        """A common-model ``target`` reuses stored raw text verbatim
        (byte-identical); an already-exported value serializes canonically."""
        options = options or {}
        if isinstance(target, (Node, Document)):
            root = target.root if isinstance(target, Document) else target
            text = _render_node(root)
        elif isinstance(target, (dict, list, str, int, float, bool)) or target is None:
            text = json.dumps(target, indent=2, ensure_ascii=False)
        else:
            raise _contract_error(f"cannot generate output for {type(target).__name__}")
        return text.encode("utf-8") if options.get("as_bytes") else text

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """JSON models none of function/method/class/module; empty ({p056})."""
        return _ROLE_MAP

    def render_document(self, document: Document) -> bytes:
        result = self.generate_output(document, {"as_bytes": True})
        if not isinstance(result, bytes):
            raise _contract_error(f"render_document expected bytes, got {type(result).__name__}")
        return result

    def render_fragment(self, node: Node) -> str:
        result = self.generate_output(node, {})
        if not isinstance(result, str):
            raise _contract_error(f"render_fragment expected str, got {type(result).__name__}")
        return result

# Ready-made singleton a sibling registry step can import and register.
JSON_FORMAT_PLUGIN = JsonFormatPlugin()
