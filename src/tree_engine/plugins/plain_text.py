"""The plain_text format plugin object itself (concept C-016, atomic step A-001).

Scope: this module is the mandatory baseline/fallback plugin ({p060}): the
degraded representation any known or explicitly-selected format falls back
to once its own ``parse_document`` has reported
``ErrorCode.FORMAT_CONTENT_PARSE_FAILED``, and an ordinary plugin in its own
right for ``.txt``/explicitly-declared text files. Unlike the Python
(LibCST) and BSL (tree-sitter-bsl) plugins, plain_text has no external
parser/codegen library to wrap: its own "parser-library representation" --
the intermediate form ``parse_document``/``parse_fragment`` build before
handing off to ``import_to_common`` -- is :class:`PlainTextTree`, a root
container plus an ordered dictionary of paragraphs keyed by fresh UUID4
identifiers, one entry per input line (line terminator included verbatim).
Order is carried three ways at once and never rebuilt from anything else:
dict insertion order in ``PlainTextTree.paragraphs``, tuple order in the
common-model root ``Node.children``, and concatenation order in
``generate_output`` -- all three are populated from one single pass over
``str.splitlines(keepends=True)``, whose per-line terminator (or lack of
one, for a final unterminated line) is kept verbatim, so no normalization,
escaping, or reflow happens anywhere in this file and paragraph
concatenation always reproduces the original decoded string exactly,
whatever mix of ``\\n``/``\\r\\n``/no-trailing-newline/blank-line/unicode
content it contains.

Two ABCs, one class: exactly as ``PythonFormatPlugin`` and
``BSLFormatPlugin`` already do, ``FormatPluginContract`` and
``FormatBoundary`` each declare an abstractmethod literally named
``parse_document`` (and, likewise, ``parse_fragment``) with different call
conventions -- ``(source, options)`` positional for the contract, ``(source,
*, source_format_id)`` for the core boundary. ``PlainTextFormatPlugin``
below satisfies both with one concrete method per name whose signature is a
superset of both call conventions; Python's ABC machinery tracks
abstractness by method *name*, so one concrete override clears the
abstractness of that name on every base that declared it.

Failure classification: undecodable input (a text-decoding error, including
truncated multi-byte content) is the only parse failure this format can
have, signaled as
``FormatPluginContractError(error_code=ErrorCode.FORMAT_CONTENT_PARSE_FAILED)``
from :func:`_decode_source`, shared by ``parse_document`` and
``parse_fragment`` alike -- no separate fragment-only failure code exists
here because plain_text has no syntax to fail on once decoding succeeds.

No external parser representation escapes this module beyond
:class:`PlainTextTree` itself: ``import_to_common``/``export_from_common``
translate between it and common-model ``Node``/``Document`` only, and
``generate_output`` produces plain ``str`` (encoded to ``bytes`` only by
``render_document``, the ``FormatBoundary``-facing counterpart).

Source-of-truth requirement labels honored here: {p022}, {p049}, {p060}.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Union
from uuid import UUID

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Document, Node, make_node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import (
    FormatPluginContract,
    FormatPluginContractError,
    FormatPluginMetadata,
    SemanticRole,
    SemanticRoleMapping,
    UnsupportedTranslationError,
)

__all__ = [
    "FORMAT_ID",
    "PlainTextTree",
    "PlainTextFormatPlugin",
    "PLAIN_TEXT_FORMAT_PLUGIN",
]

FORMAT_ID = "plain_text"
_ROOT_KIND = f"{FORMAT_ID}:root"
_PARAGRAPH_KIND = f"{FORMAT_ID}:paragraph"

# Baseline extension table entries ({p062}): ".txt" plus one explicitly
# declared text-variant extension. Additional text extensions may be added
# here later without touching any other module -- the shared registry
# treats an extension conflict with a *different* format_id as a
# configuration error, never a silent override.
_METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID,
    aliases=(),
    file_extensions=("txt", "text"),
    plugin_version="1.0.0",
    contract_version="1.0.0",
    capabilities={
        "semantic_role_mapping": True,
        "byte_identical_round_trip": True,
        "fallback_representation": True,
    },
)

# Plain text has no function/method/class construct; the whole document is
# the only thing it models, so only the root kind maps to the module role
# per SemanticRoleMapping's own documented "absent role -> empty tuple"
# contract for the roles this format does not have.
_ROLE_MAP = SemanticRoleMapping({_ROOT_KIND: SemanticRole.MODULE})


def _contract_error(
    message: str, *, code: ErrorCode = ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, error_code=code, message=message)


@dataclass
class PlainTextTree:
    """The plugin's own parser-library-equivalent representation: a root
    container plus an ordered dictionary of paragraphs, each keyed by a
    fresh UUID4 identifier assigned at append time -- the exact shape
    {p060} requires of the mandatory degraded representation. Insertion
    order is dict order (guaranteed since Python 3.7) and is the single
    source of truth for paragraph order all the way through
    ``import_to_common`` and back out through ``generate_output``."""

    paragraphs: "OrderedDict[UUID, str]" = field(default_factory=OrderedDict)

    def append_paragraph(self, text: str) -> UUID:
        """Append ``text`` as a new paragraph under a fresh UUID4 key."""

        node_id = generate_node_id()
        self.paragraphs[node_id] = text
        return node_id


def _decode_source(source: Union[str, bytes, bytearray], options: Optional[Mapping[str, Any]]) -> str:
    """Decode ``source`` to ``str``, raising ``FORMAT_CONTENT_PARSE_FAILED``
    for undecodable input (a bad encoding or truncated multi-byte content).
    ``options["encoding"]`` selects the codec, defaulting to ``"utf-8"``."""

    if isinstance(source, str):
        return source
    if isinstance(source, (bytes, bytearray)):
        encoding = (options or {}).get("encoding", "utf-8")
        try:
            return bytes(source).decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            raise _contract_error(
                f"cannot decode plain_text source as {encoding!r}: {exc}",
                code=ErrorCode.FORMAT_CONTENT_PARSE_FAILED,
            ) from exc
    raise _contract_error(
        f"plain_text source must be str or bytes, got {type(source).__name__}"
    )


def _split_paragraphs(text: str) -> PlainTextTree:
    """Split ``text`` into one paragraph per ``splitlines(keepends=True)``
    entry -- each line's own terminator (or lack of one, for a final
    unterminated line) stays attached to its paragraph text verbatim, which
    is exactly what makes concatenation byte-identical later."""

    tree = PlainTextTree()
    for line in text.splitlines(keepends=True):
        tree.append_paragraph(line)
    return tree


def _iter_paragraph_nodes(root: Node) -> Iterator[Node]:
    """Yield the paragraph nodes under ``root``, in order. ``root`` may
    itself already be a single paragraph node (the fragment case) or the
    root container (the document case); anything else is a construct this
    format cannot translate and raises :class:`UnsupportedTranslationError`
    rather than silently dropping it ({p049})."""

    if root.kind == _PARAGRAPH_KIND:
        yield root
        return
    if root.kind != _ROOT_KIND:
        raise UnsupportedTranslationError(node_type=str(root.kind), format_id=FORMAT_ID)
    for child in root.children:
        if child.kind != _PARAGRAPH_KIND:
            raise UnsupportedTranslationError(node_type=str(child.kind), format_id=FORMAT_ID)
        yield child


class PlainTextFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="plain_text"`` plugin (concept C-016).
    Reachable through exactly the same common tree interface as any other
    format plugin ({p060}): a root container ``Node`` with an ordered tuple
    of paragraph ``Node`` children, each carrying its own ``node_id``
    identity -- no format-specific escape hatch on this class's surface."""

    @property
    def metadata(self) -> FormatPluginMetadata:
        """This plugin's static identity/capability surface."""

        return _METADATA

    def parse_document(
        self,
        source: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Document:
        """Parse full source text/bytes into a common-model ``Document``.

        Input processing: ``source`` is decoded (raising
        ``FORMAT_CONTENT_PARSE_FAILED`` on undecodable content), split into
        a temporary :class:`PlainTextTree`, and handed directly to
        ``import_to_common`` -- no intermediate representation survives
        this call.
        """

        text = _decode_source(source, options)
        tree = _split_paragraphs(text)
        result = self.import_to_common(tree, options, as_document=True)
        if not isinstance(result, Document):
            raise _contract_error(
                f"parsing a full plain_text document must yield a Document, got {type(result).__name__}"
            )
        return result

    def import_external_tree(
        self, external_tree: Any, options: Optional[Mapping[str, Any]] = None
    ) -> Union[Node, Document]:
        """Translate an already-built :class:`PlainTextTree` into common
        nodes, reusing :meth:`import_to_common` -- the single shared input
        translator ({p056}, {p057})."""

        return self.import_to_common(external_tree, options, as_document=True)

    def parse_fragment(
        self,
        fragment: Union[str, bytes],
        options: Optional[Mapping[str, Any]] = None,
        *,
        source_format_id: Optional[str] = None,
    ) -> Node:
        """Parse a local fragment through the same decode/split pipeline as
        ``parse_document``, then reuse ``import_to_common``. Plain text has
        no construct it fails to recognize once decoding succeeds, so this
        never falls back to returning the fragment's own text; it always
        yields a root container ``Node`` (possibly childless, for an empty
        fragment)."""

        text = _decode_source(fragment, options)
        tree = _split_paragraphs(text)
        result = self.import_to_common(tree, options, as_document=False)
        if not isinstance(result, Node):
            raise _contract_error(
                f"parsing a plain_text fragment must yield a Node, got {type(result).__name__}"
            )
        return result

    def import_to_common(
        self,
        external_representation: Any,
        options: Optional[Mapping[str, Any]] = None,
        *,
        as_document: bool = True,
    ) -> Union[Node, Document]:
        """The single input translator shared by ``parse_document``,
        ``import_external_tree``, and ``parse_fragment``.

        Builds one paragraph ``Node`` per :class:`PlainTextTree` entry,
        each validated via ``make_node`` and then reconstructed carrying
        the same UUID4 the tree already assigned it as ``node_id`` --
        the "attach an identity produced elsewhere" pattern
        ``core/identity.py`` documents for its ``make_node``/direct-``Node``
        split. Order is preserved by iterating ``paragraphs`` in insertion
        order into ``children``. ``as_document`` selects whether the root
        is wrapped in a ``Document`` or returned bare (the fragment case);
        the extra keyword-only parameter is this plugin's own pass-through,
        as the BSL plugin adds ``fragment`` beyond its abstract signature.
        """

        if not isinstance(external_representation, PlainTextTree):
            raise _contract_error(
                f"expected a PlainTextTree, got {type(external_representation).__name__}"
            )
        children = []
        for node_id, text in external_representation.paragraphs.items():
            validated = make_node(_PARAGRAPH_KIND, fields={"text": text})
            children.append(
                Node(
                    kind=validated.kind,
                    fields=validated.fields,
                    children=validated.children,
                    node_id=node_id,
                )
            )
        validated_root = make_node(_ROOT_KIND, fields={}, children=children)
        root = Node(
            kind=validated_root.kind,
            fields=validated_root.fields,
            children=validated_root.children,
            node_id=generate_node_id(),
        )
        if as_document:
            return Document(root=root, source_format_id=FORMAT_ID)
        return root

    def export_from_common(
        self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> PlainTextTree:
        """Translate common-model nodes back into a fresh
        :class:`PlainTextTree`, preserving ``children``/dict order exactly.
        Accepts a ``Document`` (uses its ``root``) or a bare ``Node`` (the
        root container, or a single paragraph node for the fragment case).
        Any other node kind raises :class:`UnsupportedTranslationError`
        rather than being silently dropped ({p049}); an existing
        ``node_id`` is reused as the tree's key so identity survives an
        export/import round trip, and a missing one is assigned fresh.
        """

        if isinstance(nodes, Document):
            root = nodes.root
        elif isinstance(nodes, Node):
            root = nodes
        else:
            raise _contract_error(
                f"export_from_common expects a Node or Document, got {type(nodes).__name__}"
            )
        tree = PlainTextTree()
        for paragraph_node in _iter_paragraph_nodes(root):
            node_id = (
                paragraph_node.node_id
                if isinstance(paragraph_node.node_id, UUID)
                else generate_node_id()
            )
            tree.paragraphs[node_id] = paragraph_node.fields.get("text", "")
        return tree

    def generate_output(
        self,
        target: Union[Node, Document, PlainTextTree, str],
        options: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Serialize ``target`` to final plain text, preserving paragraph
        order: runs ``export_from_common`` first when given common-model
        nodes, then concatenates a backend-exported :class:`PlainTextTree`'s
        paragraph texts in order -- byte-identical to the original input
        whenever ``target`` traces back to an untouched
        ``parse_document``/``parse_fragment`` result. A plain ``str``
        passes through unchanged.
        """

        if isinstance(target, PlainTextTree):
            tree = target
        elif isinstance(target, (Node, Document)):
            tree = self.export_from_common(target, options)
        elif isinstance(target, str):
            return target
        else:
            raise _contract_error(
                f"cannot generate output for {type(target).__name__}; expected a "
                "Node, Document, PlainTextTree, or str"
            )
        return "".join(tree.paragraphs.values())

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """The declarative, context-free kind -> role table: only the root
        container maps to the module role; plain text has no function,
        method, or class construct, so those roles get no entry."""

        return _ROLE_MAP

    # -- FormatBoundary ---------------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        """CORE-facing counterpart of ``parse_document``: renders a full
        ``Document`` back to UTF-8 bytes via ``generate_output``."""

        text = self.generate_output(document, {})
        if not isinstance(text, str):
            raise _contract_error(
                f"render_document expected str from generate_output, got {type(text).__name__}"
            )
        return text.encode("utf-8")

    def render_fragment(self, node: Node) -> str:
        """CORE-facing counterpart of ``parse_fragment``: renders a single
        fragment ``Node`` back to source text via ``generate_output``."""

        text = self.generate_output(node, {})
        if not isinstance(text, str):
            raise _contract_error(
                f"render_fragment expected str from generate_output, got {type(text).__name__}"
            )
        return text


# Registration data: a ready-made, stateless singleton a sibling registry
# step (out of scope here, per {p055}/{p059}/{p101}) can import and register
# under ``format_id="plain_text"`` without needing to know how to construct
# one -- exactly the pattern ``PYTHON_FORMAT_PLUGIN``/``BSL_FORMAT_PLUGIN``
# already establish.
PLAIN_TEXT_FORMAT_PLUGIN = PlainTextFormatPlugin()
