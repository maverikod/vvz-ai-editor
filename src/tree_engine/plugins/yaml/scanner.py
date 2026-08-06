"""Lexical layer of the YAML format plugin (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the vocabulary every other module of ``tree_engine.plugins.yaml`` is
built on -- the node-kind names, the typed-error shorthands, the single-line
predicates that classify a source line, and the scalar decoders that turn one
piece of source text into a YAML 1.2 core-schema value. Nothing here knows
about block structure, node identity, or the plugin contract: that is
``reader.py``, ``emitter.py``, and ``plugin.py`` respectively. This module
imports only the standard library and the shared ``tree_engine`` error
hierarchy, never a third-party YAML library and never the legacy editor
package.

Two error vocabularies meet here and must not be confused:

* :class:`YamlSyntaxError` is package-private and purely internal. The reader
  raises it for damaged source; ``plugin.py`` is the only place allowed to
  catch it, and it converts it to ``FormatContentParseFailed`` for a whole
  document or ``FormatFragmentParseFailed`` for a fragment. It never escapes
  the plugin boundary.
* :func:`unsupported` builds the public
  ``tree_engine.exceptions.UnsupportedTranslation`` for a construct that is
  well-formed YAML but has no faithful representation in this plugin's model.
  It propagates to the caller unchanged.

:func:`contract_error` is reserved for a caller violating the calling contract
(passing a value of the wrong type); it is never used for malformed input.

Source-of-truth requirement labels honored here: {p022}, {p049}, {p062}.
"""

from __future__ import annotations

import json
import re
from typing import Union

from tree_engine.exceptions import FormatPluginContractError, UnsupportedTranslation

__all__ = [
    "FORMAT_ID",
    "KIND_DOCUMENT", "KIND_MAPPING", "KIND_PAIR", "KIND_SEQUENCE", "KIND_ITEM",
    "KIND_SCALAR", "KIND_BLOCK", "KIND_FLOW_MAPPING", "KIND_FLOW_PAIR",
    "KIND_FLOW_SEQUENCE", "KIND_FLOW_ITEM", "KIND_COMMENT", "KIND_BLANK",
    "KIND_MARKER", "KIND_TRIVIA",
    "RAW_KINDS", "STRUCTURE_KINDS", "MAPPING_KINDS", "SEQUENCE_KINDS", "PAIR_KINDS",
    "ENTRY_KINDS", "VALUE_KINDS", "TRIVIA_KINDS",
    "NO_TRANSLATION", "FLOW_OPENERS", "FLOW_INDICATORS", "BLOCK_HEADER_RE",
    "YamlSyntaxError", "syntax", "unsupported", "contract_error",
    "indent_of", "is_trivia", "is_marker", "starts_item", "find_colon", "scan_quoted",
    "fold", "decode_scalar", "decode_block",
]

FORMAT_ID = "yaml"

#: One namespaced ``NodeKind`` string per construct this plugin models. Block
#: and flow collections are deliberately distinct kinds: they carry the same
#: data but completely different source syntax, and keeping them apart is what
#: lets the emitter reproduce each one verbatim.
(KIND_DOCUMENT, KIND_MAPPING, KIND_PAIR, KIND_SEQUENCE, KIND_ITEM, KIND_SCALAR,
 KIND_BLOCK, KIND_FLOW_MAPPING, KIND_FLOW_PAIR, KIND_FLOW_SEQUENCE, KIND_FLOW_ITEM,
 KIND_COMMENT, KIND_BLANK, KIND_MARKER, KIND_TRIVIA) = [
    f"{FORMAT_ID}:{name}" for name in (
        "Document", "Mapping", "Pair", "Sequence", "Item", "Scalar", "BlockScalar",
        "FlowMapping", "FlowPair", "FlowSequence", "FlowItem",
        "Comment", "Blank", "Marker", "Trivia")]

#: Leaf kinds whose whole source text is stored verbatim in ``fields["raw"]``.
RAW_KINDS = (KIND_COMMENT, KIND_BLANK, KIND_MARKER, KIND_SCALAR, KIND_BLOCK)

#: Kinds rendered as ``head + rendered children + tail``. Block containers
#: simply carry no head or tail, so one uniform rule covers every one of them.
STRUCTURE_KINDS = (KIND_DOCUMENT, KIND_MAPPING, KIND_SEQUENCE, KIND_TRIVIA,
                   KIND_FLOW_MAPPING, KIND_FLOW_SEQUENCE,
                   KIND_PAIR, KIND_ITEM, KIND_FLOW_PAIR, KIND_FLOW_ITEM)

MAPPING_KINDS = (KIND_MAPPING, KIND_FLOW_MAPPING)
SEQUENCE_KINDS = (KIND_SEQUENCE, KIND_FLOW_SEQUENCE)
PAIR_KINDS = (KIND_PAIR, KIND_FLOW_PAIR)
ENTRY_KINDS = (KIND_PAIR, KIND_ITEM, KIND_FLOW_PAIR, KIND_FLOW_ITEM)
VALUE_KINDS = (KIND_MAPPING, KIND_SEQUENCE, KIND_SCALAR, KIND_BLOCK,
               KIND_FLOW_MAPPING, KIND_FLOW_SEQUENCE)
TRIVIA_KINDS = (KIND_COMMENT, KIND_BLANK)

#: Anchor, alias, tag and explicit-key indicators. Each of these carries
#: identity or type information that this plugin's model cannot reproduce, so
#: every one of them raises ``UNSUPPORTED_TRANSLATION`` instead of being
#: silently flattened.
NO_TRANSLATION = "&*!?"
FLOW_OPENERS = "{["
FLOW_INDICATORS = ",{}[]"

_INT_RE = re.compile(r"[-+]?[0-9]+")
_FLOAT_RE = re.compile(
    r"[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.[0-9]*)(?:[eE][-+]?[0-9]+)?|[-+]?[0-9]+[eE][-+]?[0-9]+")
#: A block-scalar header: the style indicator plus optional explicit indent
#: and chomping indicators, in either order (``|``, ``>-``, ``|2+``, ...).
BLOCK_HEADER_RE = re.compile(r"[|>](?:[1-9][+-]?|[+-]?[1-9]?)")


class YamlSyntaxError(Exception):
    """Package-private malformed-YAML signal.

    Raised by the reader, caught only in ``plugin.py``, and translated there
    into the public ``FormatContentParseFailed`` / ``FormatFragmentParseFailed``
    exception appropriate to the call. It never crosses the plugin boundary.
    """


def syntax(message: str, number: int) -> YamlSyntaxError:
    """Build a :class:`YamlSyntaxError` naming the 1-based source line."""

    return YamlSyntaxError(f"{message} (line {number})")


def unsupported(node_type: str, message: str) -> UnsupportedTranslation:
    """Build the public ``UNSUPPORTED_TRANSLATION`` error for ``node_type``."""

    return UnsupportedTranslation(message, node_type=node_type, format_id=FORMAT_ID)


def contract_error(message: str) -> FormatPluginContractError:
    """Build the ``FORMAT_PLUGIN_CONTRACT_ERROR`` for a bad caller argument."""

    return FormatPluginContractError(message, plugin_id=FORMAT_ID)


def indent_of(line: str) -> int:
    """Return the number of leading spaces on ``line``."""

    return len(line) - len(line.lstrip(" "))


def is_trivia(line: str) -> bool:
    """Return whether ``line`` is blank or holds nothing but a comment."""

    return not line.strip() or line.lstrip(" ").startswith("#")


def is_marker(line: str) -> bool:
    """Return whether ``line`` is a ``---`` or ``...`` document marker."""

    text = line.rstrip("\r\n")
    return text in ("---", "...") or text[:4] in ("--- ", "... ")


def starts_item(line: str, indent: int) -> bool:
    """Return whether ``line`` carries a block-sequence ``-`` marker at ``indent``.

    The dash must be followed by whitespace or the line end; ``-1`` is a
    scalar, not a sequence entry.
    """

    if indent >= len(line) or line[indent] != "-":
        return False
    return indent + 1 >= len(line) or line[indent + 1] in " \t\r\n"


def find_colon(line: str, start: int) -> int:
    """Return the index of the ``key: value`` separator at/after ``start``, else ``-1``.

    A token that opens with a quote is skipped whole, so a ``:`` inside a
    quoted scalar can never masquerade as a mapping separator. A token that
    opens a flow collection is rejected outright: a flow collection is a value
    or a whole node, never the start of a block mapping key here.
    """

    index = start
    if index < len(line) and line[index] in FLOW_OPENERS:
        return -1
    if index < len(line) and line[index] in "\"'":
        try:
            index = scan_quoted(line, index, 0)
        except YamlSyntaxError:
            return -1
    while index < len(line):
        char = line[index]
        if char in "\r\n" or (char == "#" and index > start and line[index - 1] == " "):
            return -1
        if char == ":" and (index + 1 >= len(line) or line[index + 1] in " \r\n"):
            return index
        index += 1
    return -1


def scan_quoted(text: str, start: int, number: int) -> int:
    """Return the index just past the quoted scalar beginning at ``start``.

    ``text`` bounds the scan, and that is deliberate: callers pass a single
    line when a construct may not span lines (a block mapping key) and the
    whole document when it may (any quoted value), so one function serves
    both without a mode flag.
    """

    quote, index = text[start], start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and quote == '"':
            index += 2
        elif char == quote:
            if quote == "'" and text[index + 1:index + 2] == "'":
                index += 2  # a doubled single quote is an escaped quote
                continue
            return index + 1
        else:
            index += 1
    raise syntax("unterminated quoted scalar", number)


def fold(text: str) -> str:
    """Apply YAML flow folding to a multi-line scalar's content.

    A single line break folds into one space; a run of *n* consecutive breaks
    yields *n - 1* newlines. The intermediate NUL sentinel keeps the newlines
    produced by the first pass from being folded away by the second.
    """

    if "\n" not in text:
        return text
    folded = re.sub(r"[ \t]*\n(?:[ \t]*\n)+[ \t]*",
                    lambda run: "\x00" * (run.group(0).count("\n") - 1), text)
    return re.sub(r"[ \t]*\n[ \t]*", " ", folded).replace("\x00", "\n")


def decode_scalar(raw: str) -> Union[str, int, float, bool, None]:
    """Decode one scalar's source text into a YAML 1.2 core-schema value.

    Double-quoted scalars go through the JSON string decoder, which shares
    YAML's escape vocabulary for everything except the two YAML-only forms
    handled first: a backslash before a line break suppresses that break
    entirely, and ``"\\ "`` is an escaped space used to protect leading
    whitespace. Anything the decoder still rejects falls back to the folded
    body rather than raising -- a scalar's exact source text is preserved
    separately, so a decode fallback can never cost byte fidelity.
    """

    if raw.startswith('"'):
        body = fold(re.sub(r"\\\n[ \t]*", "", raw[1:-1]))
        body = re.sub(r"(?<!\\)((?:\\\\)*)\\ ", r"\1 ", body)
        try:
            return json.loads(f'"{body}"')
        except ValueError:
            return body
    raw = fold(raw)
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


def decode_block(style: str, lines: "list[str]", indent: int) -> str:
    """Decode a literal (``|``) or folded (``>``) block scalar body.

    ``style`` is the header text, ``lines`` the body lines with their
    terminators, ``indent`` the owning entry's indentation. An explicit indent
    digit is relative to ``indent``; without one the first non-empty line sets
    the content indentation. Chomping is applied last: ``-`` strips every
    trailing newline, ``+`` keeps them all, and the default clips to one.
    """

    digits = [char for char in style if char.isdigit()]
    chomp = "+" if "+" in style else ("-" if "-" in style else "")
    body = [line.rstrip("\n").rstrip("\r") for line in lines]
    width = (indent + int(digits[0])) if digits else next(
        (indent_of(line) for line in body if line.strip()), 0)
    rows = [line[width:] if len(line) > width else "" for line in body]
    if style[0] == "|":
        text = "".join(row + "\n" for row in rows)
    else:
        pieces = rows[:1]
        for position in range(1, len(rows)):
            row, previous = rows[position], rows[position - 1]
            # A break folds into a space only between two non-empty lines that
            # are both at the content indentation; anything else keeps it.
            folded = row and previous and row[0] != " " and previous[0] != " "
            pieces.append((" " if folded else "\n") + row)
        text = ("".join(pieces) + "\n") if rows else ""
    core = text.rstrip("\n")
    if chomp:
        return core if chomp == "-" else text
    return core + "\n" if core else ""
