"""Flow-collection reading for the YAML plugin (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: YAML's inline collection syntax -- flow mappings ``{a: 1}`` and flow
sequences ``[1, 2]`` -- read structurally into common-model nodes without
losing a byte. Block structure lives in :mod:`.reader`, which inherits
:class:`FlowReader` and supplies the attributes used here.

Flow collections are ordinary YAML, not an exotic corner: roughly two in five
real documents use them. They are therefore modelled properly -- one node per
collection, one entry node per element, a real key and value on every pair --
and not flattened into opaque text.

The byte-fidelity scheme ({p022}) assigns every character to exactly one
owner, which is what lets inner spacing, trailing commas, comments inside a
collection and multi-line layout all survive a round trip:

* the container's ``head`` is its opening bracket plus everything up to the
  first entry (so ``[ ]`` keeps its space);
* each entry's ``tail`` is everything from the end of that entry up to the
  start of the next one -- whitespace, line breaks, the comma, any comment;
* the container's ``tail`` is the closing bracket alone.

Concatenating head, entries and tail therefore reproduces the source exactly.

Source-of-truth requirement labels honored here: {p022}, {p049}, {p062}.
"""

from __future__ import annotations

import bisect
from typing import Any, Dict, List, Tuple

from tree_engine.core.nodes import Node
from tree_engine.plugins.yaml.builder import NodeBuilder
from tree_engine.plugins.yaml.scanner import (
    FLOW_INDICATORS, FLOW_OPENERS, KIND_FLOW_ITEM, KIND_FLOW_MAPPING, KIND_FLOW_PAIR,
    KIND_FLOW_SEQUENCE, KIND_SCALAR, NO_TRANSLATION, decode_scalar, scan_quoted, syntax,
    unsupported,
)

__all__ = ["ANCHOR_MESSAGE", "FlowReader"]

#: Shared wording for every anchor/alias/tag/explicit-key refusal, so the
#: block reader and the flow reader report the same construct identically.
ANCHOR_MESSAGE = "(anchor/alias/tag/explicit key) cannot round-trip faithfully"

#: Characters that may follow a ``:`` for it to read as a flow key separator.
_AFTER_COLON = ("", " ", "\t", "\r", "\n", ",", "}", "]", "{", "[")


class FlowReader:
    """Reads YAML flow collections; a base of the full reader, never used alone.

    The subclass provides ``text`` (the whole source), ``starts`` (the offset
    each line begins at, used only to turn an offset into a line number for
    error messages) and ``builder`` (the identity-assigning node factory).
    Every offset in this class is an absolute index into ``text``, because a
    flow collection may span any number of lines.
    """

    text: str
    starts: List[int]
    builder: NodeBuilder

    def _line(self, offset: int) -> int:
        """Return the 1-based source line number containing ``offset``."""

        return bisect.bisect_right(self.starts, offset)

    def _flow_skip(self, offset: int) -> int:
        """Skip whitespace, line breaks and comments inside a flow collection.

        Only ever called where a separator is expected, so a ``#`` here always
        opens a comment and never belongs to a scalar.
        """

        while offset < len(self.text):
            char = self.text[offset]
            if char in " \t\r\n":
                offset += 1
            elif char == "#":
                newline = self.text.find("\n", offset)
                offset = len(self.text) if newline < 0 else newline
            else:
                break
        return offset

    def _flow_token_end(self, offset: int) -> int:
        """Return the end offset of one plain or quoted token in flow context.

        A quoted token is delimited by its quotes and may contain any flow
        indicator; that is what keeps ``"a,b"`` and ``'{x}'`` in one piece. A
        plain token ends at a flow indicator, at a ``:`` acting as a key
        separator, at a comment, or at the line end. Trailing spaces are
        excluded so they fall into the surrounding span instead.
        """

        if self.text[offset] in "\"'":
            return scan_quoted(self.text, offset, self._line(offset))
        end = offset
        while end < len(self.text):
            char = self.text[end]
            if char in FLOW_INDICATORS or char == "\n":
                break
            if char == ":" and self.text[end + 1:end + 2] in _AFTER_COLON:
                break
            if char == "#" and end > offset and self.text[end - 1] == " ":
                break
            end += 1
        while end > offset and self.text[end - 1] in " \t\r":
            end -= 1
        return end

    def _flow_value(self, offset: int) -> Tuple[Node, int]:
        """Read one value inside a flow collection: a nested flow, or a scalar."""

        char = self.text[offset]
        if char in NO_TRANSLATION:
            raise unsupported("Anchored", f"YAML indicator {char!r} {ANCHOR_MESSAGE}")
        if char in FLOW_OPENERS:
            return self.read_flow(offset)
        end = self._flow_token_end(offset)
        raw = self.text[offset:end]
        if not raw:
            raise syntax("empty value in a flow collection", self._line(offset))
        fields = {"raw": raw, "value": decode_scalar(raw),
                  "style": raw[0] if raw[0] in "\"'" else "plain"}
        return self.builder.node(KIND_SCALAR, fields), end

    def _flow_entry(self, offset: int, entry_kind: str) -> Tuple[Node, int]:
        """Read one flow entry together with the separator span that follows it."""

        fields: Dict[str, Any] = {}
        if entry_kind == KIND_FLOW_PAIR:
            key_end = self._flow_token_end(offset)
            key_raw = self.text[offset:key_end]
            if not key_raw:
                raise syntax("empty key in a flow mapping", self._line(offset))
            if key_raw[0] in NO_TRANSLATION:
                raise unsupported("Anchored", f"YAML indicator {key_raw[0]!r} {ANCHOR_MESSAGE}")
            if key_raw.startswith("<<"):
                raise unsupported("MergeKey",
                                  "YAML merge keys ('<<') cannot round-trip faithfully")
            colon = self._flow_skip(key_end)
            if self.text[colon:colon + 1] == ":":
                value_at = self._flow_skip(colon + 1)
                value, cursor = self._flow_value(value_at)
                fields["head"] = self.text[offset:value_at]
            else:  # a valueless entry: YAML's set-like "{a, b}" form
                value, cursor = None, key_end
                fields["head"] = key_raw
            fields.update(key=decode_scalar(key_raw), key_raw=key_raw)
        else:
            value, cursor = self._flow_value(offset)
            fields["head"] = ""
        separator = cursor
        cursor = self._flow_skip(cursor)
        if self.text[cursor:cursor + 1] == ",":
            cursor = self._flow_skip(cursor + 1)
        fields["tail"] = self.text[separator:cursor]
        children = (value,) if value is not None else ()
        return self.builder.node(entry_kind, fields, children), cursor

    def read_flow(self, offset: int) -> Tuple[Node, int]:
        """Read the flow collection opening at ``offset``; return it and its end.

        Flow collections nest freely and may span any number of lines. An
        unterminated one, or one closed by the wrong bracket, is damaged
        source and raises the package-private syntax signal rather than an
        unsupported-translation error.
        """

        opener = self.text[offset]
        closer = "]" if opener == "[" else "}"
        sequence = opener == "["
        cursor = self._flow_skip(offset + 1)
        head = self.text[offset:cursor]
        children: List[Node] = []
        while True:
            if cursor >= len(self.text):
                raise syntax("unterminated flow collection", self._line(offset))
            if self.text[cursor] == closer:
                break
            if self.text[cursor] in "}]":
                raise syntax(f"expected {closer!r} in a flow collection", self._line(cursor))
            entry, after = self._flow_entry(
                cursor, KIND_FLOW_ITEM if sequence else KIND_FLOW_PAIR)
            if after <= cursor:  # a guard: an entry must always consume input
                raise syntax("cannot classify flow collection content", self._line(cursor))
            children.append(entry)
            cursor = after
        kind = KIND_FLOW_SEQUENCE if sequence else KIND_FLOW_MAPPING
        return self.builder.node(kind, {"head": head, "tail": closer}, children), cursor + 1
