"""The plain_text format plugin object itself (concept C-016, atomic step A-001).

Scope: this module is the mandatory baseline/fallback plugin ({p060}) -- the
degraded representation any known or explicitly-selected format falls back to
once its own ``parse_document`` has reported
``ErrorCode.FORMAT_CONTENT_PARSE_FAILED`` -- and an ordinary plugin in its own
right for ``.txt``/explicitly-declared text files. Unlike the Python (LibCST)
and BSL (tree-sitter-bsl) plugins it has no external parser/codegen library to
wrap: its own "parser-library representation", the intermediate form
``parse_document``/``parse_fragment`` build before handing off to
``import_to_common``, is :class:`PlainTextTree` -- a root container plus an
ordered dictionary of paragraphs keyed by fresh UUID4 identifiers, one entry
per input line (terminator included verbatim). Order is carried three ways at
once and never rebuilt: dict insertion order in ``PlainTextTree.paragraphs``,
tuple order in the common-model root ``Node.children``, and concatenation
order in ``generate_output`` -- all three populated from one single pass over
``str.splitlines(keepends=True)``. No normalization, escaping, or reflow
happens anywhere in this file, so paragraph concatenation always reproduces
the original decoded string exactly, whatever mix of line endings, blank
lines, missing trailing newline, or unicode content it contains.

Two ABCs, one class: as ``PythonFormatPlugin``/``BSLFormatPlugin`` already do,
``FormatPluginContract`` and ``FormatBoundary`` each declare an abstractmethod
named ``parse_document`` (likewise ``parse_fragment``) with different call
conventions -- ``(source, options)`` positional for the contract, ``(source,
*, source_format_id)`` for the core boundary. ``PlainTextFormatPlugin``
satisfies both with one concrete method per name whose signature is a superset
of both; Python's ABC machinery tracks abstractness by method *name*.

Failure classification: undecodable input (a text-decoding error, including
truncated multi-byte content) is the only parse failure this format can have,
signaled as ``FormatPluginContractError(error_code=ErrorCode.FORMAT_CONTENT_PARSE_FAILED)``
from :func:`_decode_source`, shared by ``parse_document`` and
``parse_fragment`` alike -- plain_text has no syntax to fail on once decoding
succeeds, so there is no fragment-only failure code.

No external parser representation escapes this module beyond
:class:`PlainTextTree`: ``import_to_common``/``export_from_common`` translate
between it and common-model ``Node``/``Document`` only, and
``generate_output`` produces plain ``str`` (encoded to ``bytes`` only by
``render_document``, the ``FormatBoundary``-facing counterpart).

Source-of-truth requirement labels honored here: {p022}, {p049}, {p060}.
"""

from __future__ import annotations

import itertools
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
    "VERBATIM_TEXT_FIELD",
    "PlainTextTree",
    "PlainTextFormatPlugin",
    "PLAIN_TEXT_FORMAT_PLUGIN",
]

FORMAT_ID = "plain_text"
_ROOT_KIND = f"{FORMAT_ID}:root"
_PARAGRAPH_KIND = f"{FORMAT_ID}:paragraph"

#: Optional paragraph-node field naming the *verbatim* source slice a
#: paragraph stands for. ``export_from_common`` renders it in preference to
#: ``"text"``, so a producer of ``plain_text:paragraph`` nodes that does not
#: come through ``parse_document`` -- ``plugins/fallback.py``, whose ``"text"``
#: is a normalized, human-facing view of a blank-line-delimited paragraph --
#: still renders back as the exact original bytes. Nodes built by this plugin
#: never carry it, their ``"text"`` being verbatim already, so none of this
#: plugin's own paths change.
VERBATIM_TEXT_FIELD = "source_text"

# Baseline extension table entries ({p062}): ".txt" plus one explicitly
# declared text-variant extension. More may be added here later without
# touching any other module -- the shared registry treats an extension
# conflict with a *different* format_id as a configuration error.
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

# Plain text has no function/method/class construct, so only the root kind
# maps to the module role, per SemanticRoleMapping's documented
# "absent role -> empty tuple" contract for the roles it does not have.
_ROLE_MAP = SemanticRoleMapping({_ROOT_KIND: SemanticRole.MODULE})

# Every node built here gets a node_id plus a compact short_id ({p097}),
# from one module-level counter shared by all of them.
_short_id_counter = itertools.count(1)


def _contract_error(
    message: str, *, code: ErrorCode = ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
) -> FormatPluginContractError:
    return FormatPluginContractError(plugin_id=FORMAT_ID, error_code=code, message=message)


@dataclass
class PlainTextTree:
    """The plugin's own parser-library-equivalent representation: a root
    container plus an ordered dictionary of paragraphs, each keyed by a fresh
    UUID4 assigned at append time -- the exact shape {p060} requires of the
    mandatory degraded representation. Insertion order is dict order, the
    single source of truth for paragraph order through ``import_to_common``
    and back out through ``generate_output``."""

    paragraphs: "OrderedDict[UUID, str]" = field(default_factory=OrderedDict)

    def append_paragraph(self, text: str) -> UUID:
        """Append ``text`` as a new paragraph under a fresh UUID4 key."""

        node_id = generate_node_id()
        self.paragraphs[node_id] = text
        return node_id


def _decode_source(source: Union[str, bytes, bytearray], options: Optional[Mapping[str, Any]]) -> str:
    """Decode ``source`` to ``str``, raising ``FORMAT_CONTENT_PARSE_FAILED`` for
    undecodable input (bad encoding or truncated multi-byte content).
    ``options["encoding"]`` selects the codec, default ``"utf-8"``."""

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
    unterminated line) stays attached verbatim, which is what makes
    concatenation byte-identical later."""

    tree = PlainTextTree()
    for line in text.splitlines(keepends=True):
        tree.append_paragraph(line)
    return tree


def _iter_paragraph_nodes(root: Node) -> Iterator[Node]:
    """Yield the paragraph nodes under ``root``, in order. ``root`` may itself
    be a single paragraph node (the fragment case) or the root container (the
    document case); anything else raises :class:`UnsupportedTranslationError`
    rather than being dropped ({p049})."""

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
    """The registered ``format_id="plain_text"`` plugin (concept C-016),
    reachable through the same common tree interface as any other format
    plugin ({p060}): a root container ``Node`` with an ordered tuple of
    paragraph ``Node`` children, each carrying its own ``node_id`` identity."""

    #: Kinds :meth:`parse_fragment` wraps a caller's content in rather than
    #: returning as content itself. ``plain_text`` has no fragment node type of
    #: its own -- a fragment is parsed by the very same split as a document --
    #: so its result is always the root container, and splicing that container
    #: in beside a paragraph produces a tree ``generate_output`` refuses with
    #: ``UnsupportedTranslationError``: nothing but a paragraph may sit under
    #: the root. Declaring the kind here lets a caller performing a splice
    #: (``facade._fragment``) take the children instead, without having to know
    #: that plain_text in particular does this, and without any format whose
    #: fragment result IS content -- JSON's object, Python's statement -- being
    #: unwrapped by the same rule. ``_ROOT_KIND`` remains a perfectly legal
    #: PARSE result; this says only that it is a wrapper, never content.
    fragment_container_kinds = (_ROOT_KIND,)

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
        """Parse full source text/bytes into a common-model ``Document``:
        ``source`` is decoded (raising ``FORMAT_CONTENT_PARSE_FAILED`` on
        undecodable content), split into a temporary :class:`PlainTextTree`,
        and handed to ``import_to_common``; no intermediate form survives."""

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
        nodes, reusing :meth:`import_to_common`, the single shared input
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
        ``parse_document``, then reuse ``import_to_common``. Plain text has no
        construct it fails to recognize once decoding succeeds, so this never
        returns the fragment's own text; it always yields a root container
        ``Node`` (childless for an empty fragment)."""

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

        Builds one paragraph ``Node`` per :class:`PlainTextTree` entry, each
        validated via ``make_node`` then reconstructed carrying the UUID4 the
        tree already assigned it -- the "attach an identity produced
        elsewhere" pattern ``core/identity.py`` documents. Order is preserved
        by iterating ``paragraphs`` in insertion order into ``children``.
        ``as_document`` selects a ``Document`` wrapper or a bare root (the
        fragment case); that keyword-only parameter is this plugin's own
        pass-through, as BSL adds ``fragment`` to its own.
        """

        if not isinstance(external_representation, PlainTextTree):
            raise _contract_error(
                f"expected a PlainTextTree, got {type(external_representation).__name__}"
            )
        children = []
        for node_id, text in external_representation.paragraphs.items():
            validated = make_node(_PARAGRAPH_KIND, fields={"text": text})
            children.append(Node(
                kind=validated.kind, fields=validated.fields, children=validated.children,
                node_id=node_id, short_id=next(_short_id_counter),
            ))
        validated_root = make_node(_ROOT_KIND, fields={}, children=children)
        root = Node(
            kind=validated_root.kind, fields=validated_root.fields, children=validated_root.children,
            node_id=generate_node_id(), short_id=next(_short_id_counter),
        )
        if as_document:
            return Document(root=root, source_format_id=FORMAT_ID)
        return root

    def export_from_common(
        self, nodes: Union[Node, Document], options: Optional[Mapping[str, Any]] = None
    ) -> PlainTextTree:
        """Translate common-model nodes back into a fresh
        :class:`PlainTextTree`, preserving ``children``/dict order exactly.
        Accepts a ``Document`` (uses its ``root``) or a bare ``Node`` (root
        container, or a single paragraph node for the fragment case). Any
        other kind raises :class:`UnsupportedTranslationError` rather than
        being silently dropped ({p049}); an existing ``node_id`` is reused as
        the tree's key so identity survives a round trip.

        A paragraph carrying :data:`VERBATIM_TEXT_FIELD` exports that slice
        instead of ``"text"``, so a foreign producer of paragraph nodes can
        keep a normalized ``"text"`` and still render byte-identically.
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
            verbatim = paragraph_node.fields.get(VERBATIM_TEXT_FIELD)
            tree.paragraphs[node_id] = (
                verbatim if isinstance(verbatim, str) else paragraph_node.fields.get("text", "")
            )
        return tree

    def generate_output(
        self,
        target: Union[Node, Document, PlainTextTree, str],
        options: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Serialize ``target`` to final plain text, preserving paragraph
        order: runs ``export_from_common`` when given common-model nodes, then
        concatenates the exported :class:`PlainTextTree`'s paragraph texts in
        order -- byte-identical to the original input whenever ``target``
        traces back to an untouched parse result. A ``str`` passes through.
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
        container maps to the module role; plain text has no function, method,
        or class construct, so those roles get no entry."""

        return _ROLE_MAP

    # -- FormatBoundary ---------------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        """CORE-facing counterpart of ``parse_document``: renders a full
        ``Document`` back to UTF-8 bytes via ``generate_output``.

        Encoded with ``errors="surrogateescape"`` so content that reached
        the common model through a surrogateescape decode (the fallback
        rescuing a file whose bytes are not valid UTF-8) is written back as
        exactly those bytes instead of raising; for a string without lone
        surrogates this is identical to a strict UTF-8 encode.
        """

        text = self.generate_output(document, {})
        if not isinstance(text, str):
            raise _contract_error(
                f"render_document expected str from generate_output, got {type(text).__name__}"
            )
        return text.encode("utf-8", errors="surrogateescape")

    def render_fragment(self, node: Node) -> str:
        """CORE-facing counterpart of ``parse_fragment``: renders one
        fragment ``Node`` back to source text via ``generate_output``."""

        text = self.generate_output(node, {})
        if not isinstance(text, str):
            raise _contract_error(
                f"render_fragment expected str from generate_output, got {type(text).__name__}"
            )
        return text


# Registration data: a ready-made, stateless singleton a sibling registry
# step (out of scope here, per {p055}/{p059}/{p101}) can import and register
# under ``format_id="plain_text"``, exactly as
# ``PYTHON_FORMAT_PLUGIN``/``BSL_FORMAT_PLUGIN`` already establish.
PLAIN_TEXT_FORMAT_PLUGIN = PlainTextFormatPlugin()
