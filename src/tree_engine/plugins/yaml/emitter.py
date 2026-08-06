"""Output side of the YAML format plugin (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: everything that leaves the common model. Three separate jobs live here
and they must not be confused with one another:

* :func:`render` replays a tree that came from :mod:`.reader`, reassembling
  each node from the verbatim text its own fields hold. This is the path that
  makes ``render_document(parse_document(source)) == source`` true byte for
  byte ({p022}). It is bottom-up: a node's output is its own head, then its
  live children's output, then its own tail, so a replaced subtree really does
  change the result instead of a stale copy of the original text winning.
* :func:`node_to_plain` projects the model onto ordinary Python data
  (``dict``/``list``/scalars), discarding trivia. This is what
  ``export_from_common`` hands to callers who want the data, not the document.
* :func:`plain_to_node` and :func:`emit` are the reverse direction for a tree
  that never had source text: nodes built from a plain Python value carry no
  ``raw``/``head``/``tail``, so they are written out in a deterministic
  canonical style instead of replayed. :func:`is_source_tree` is the test that
  decides which of the two paths applies.

Source-of-truth requirement labels honored here: {p022}, {p049}, {p056}.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from tree_engine.core.nodes import Node
from tree_engine.plugins.yaml.builder import NodeBuilder
from tree_engine.plugins.yaml.scanner import (
    ENTRY_KINDS, KIND_BLOCK, KIND_DOCUMENT, KIND_ITEM, KIND_MAPPING, KIND_PAIR,
    KIND_SCALAR, KIND_SEQUENCE, KIND_TRIVIA, MAPPING_KINDS, PAIR_KINDS, RAW_KINDS,
    SEQUENCE_KINDS, STRUCTURE_KINDS, TRIVIA_KINDS, VALUE_KINDS, decode_scalar, unsupported,
)

__all__ = ["render", "is_source_tree", "node_to_plain", "plain_to_node",
           "emit_scalar", "emit"]

#: Characters that make a plain scalar ambiguous when they open it, so a
#: string starting with one must be quoted on the canonical output path.
_UNSAFE_LEAD = "#&*!?|>%@`{}[],'\"-"


def render(node: Node) -> str:
    """Replay a parsed tree's verbatim source text, bottom-up ({p022}).

    Leaves carry their whole text in ``raw``; every structural node renders as
    its ``head``, then its children, then its ``tail``. Block containers
    simply hold neither, which is why one rule covers documents, block
    mappings and sequences, flow collections and every entry kind alike.
    """

    if node.kind in RAW_KINDS:
        raw = node.fields.get("raw")
        if not isinstance(raw, str):
            raise unsupported(str(node.kind), "node carries no verbatim 'raw' text")
        return raw
    if node.kind not in STRUCTURE_KINDS:
        raise unsupported(str(node.kind), f"node kind {node.kind!r} has no YAML representation")
    head, tail = node.fields.get("head", ""), node.fields.get("tail", "")
    if not isinstance(head, str) or not isinstance(tail, str):
        raise unsupported(str(node.kind), "node carries no verbatim head/tail text")
    return head + "".join(render(child) for child in node.children) + tail


def is_source_tree(node: Node) -> bool:
    """Return whether ``node`` came from parsing and can be replayed verbatim.

    Only the reader attaches ``raw``/``head``/``tail``; a tree built by
    :func:`plain_to_node` carries neither, and must be emitted canonically.
    """

    if node.kind == KIND_DOCUMENT:
        return True
    if "raw" in node.fields or "head" in node.fields:
        return True
    return any(is_source_tree(child) for child in node.children)


def node_to_plain(node: Node) -> Any:
    """Project common-model nodes onto plain YAML-compatible Python data.

    Trivia is dropped: comments and blank lines are part of the document, not
    of its data. A document holding several YAML documents yields a list of
    their values, one holding a single document yields that value directly.
    """

    if node.kind == KIND_DOCUMENT:
        values = [node_to_plain(child) for child in node.children if child.kind in VALUE_KINDS]
        return (values[0] if len(values) == 1 else values) if values else None
    if node.kind in MAPPING_KINDS:
        result: Dict[Any, Any] = {}
        for pair in node.children:
            if pair.kind in PAIR_KINDS:
                result[pair.fields.get("key")] = node_to_plain(pair)
            elif pair.kind not in TRIVIA_KINDS:
                raise unsupported(str(pair.kind), "unexpected child of a YAML mapping")
        return result
    if node.kind in SEQUENCE_KINDS:
        return [node_to_plain(item) for item in node.children if item.kind not in TRIVIA_KINDS]
    if node.kind in ENTRY_KINDS:
        return node_to_plain(node.children[0]) if node.children else None
    if node.kind in (KIND_SCALAR, KIND_BLOCK):
        return node.fields.get("value")
    if node.kind == KIND_TRIVIA:
        return None
    raise unsupported(str(node.kind), f"node kind {node.kind!r} has no YAML value")


def plain_to_node(builder: NodeBuilder, value: Any, seen: frozenset) -> Node:
    """Build raw-less nodes from a plain Python value, for canonical output.

    ``seen`` carries the ``id()`` of every container on the recursion path, so
    a self-referential structure raises ``UNSUPPORTED_TRANSLATION`` instead of
    recursing forever. Block kinds are used throughout: a value with no source
    text has no flow-versus-block style to preserve.
    """

    if isinstance(value, (dict, list, tuple)):
        if id(value) in seen:
            raise unsupported(type(value).__name__, "circular reference detected")
        deep = seen | {id(value)}
        if isinstance(value, dict):
            return builder.node(KIND_MAPPING, {}, [
                builder.node(KIND_PAIR, {"key": key}, (plain_to_node(builder, item, deep),))
                for key, item in value.items()])
        return builder.node(KIND_SEQUENCE, {}, [
            builder.node(KIND_ITEM, {}, (plain_to_node(builder, item, deep),))
            for item in value])
    if value is None or isinstance(value, (str, int, float, bool)):
        return builder.node(KIND_SCALAR, {"value": value})
    raise unsupported(type(value).__name__,
                      f"Python type {type(value).__name__!r} has no YAML representation")


def emit_scalar(value: Any) -> str:
    """Render one plain value as canonical YAML scalar text.

    A string is quoted whenever its plain form would not read back as the same
    string -- empty, padded, opening with an indicator, containing ``": "``,
    spanning lines, or decoding as a number, boolean or null.
    """

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, (list, tuple)):
        return "[]"
    if not isinstance(value, str):
        raise unsupported(type(value).__name__,
                          f"Python type {type(value).__name__!r} has no YAML representation")
    if (not value or value != value.strip() or value[0] in _UNSAFE_LEAD
            or ": " in value or value.endswith(":") or "\n" in value
            or decode_scalar(value) != value):
        return json.dumps(value, ensure_ascii=False)
    return value


def emit(value: Any, indent: int) -> str:
    """Write plain Python data as deterministic canonical block YAML.

    Two-space indentation, block style throughout, one entry per line, and an
    empty collection as ``{}``/``[]``. Used only for trees with no original
    source text; anything that came from the reader is replayed by
    :func:`render` instead.
    """

    pad = "  " * indent
    if isinstance(value, dict) and value:
        return "".join(
            f"{pad}{emit_scalar(key)}:\n" + emit(item, indent + 1)
            if isinstance(item, (dict, list, tuple)) and item
            else f"{pad}{emit_scalar(key)}: {emit_scalar(item)}\n"
            for key, item in value.items())
    if isinstance(value, (list, tuple)) and value:
        return "".join(
            f"{pad}-\n" + emit(item, indent + 1)
            if isinstance(item, (dict, list, tuple)) and item
            else f"{pad}- {emit_scalar(item)}\n"
            for item in value)
    return pad + emit_scalar(value) + "\n"
