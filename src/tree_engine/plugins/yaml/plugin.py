"""The YAML format plugin surface (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the contract surface itself -- published metadata, the pipeline stages
of ``FormatPluginContract``, the CORE-side ``FormatBoundary`` methods, and the
ready-made ``YAML_FORMAT_PLUGIN`` singleton a sibling registry step registers
under ``format_id="yaml"`` for the ``.yaml``/``.yml`` extensions. The work
itself lives in the package's other modules: :mod:`.scanner` (lexical layer),
:mod:`.builder` (node identity), :mod:`.reader` and :mod:`.flow` (source text
to common-model nodes) and :mod:`.emitter` (common model back out). This
package is standalone -- standard library plus sibling
``tree_engine`` modules only, no third-party YAML library and nothing from the
legacy editor package.

Supported subset: block mappings; block sequences, including the compact
``- key: value`` form and the form that sits at the same indentation as its
key; flow mappings ``{a: 1}`` and flow sequences ``[1, 2]``, nested freely,
spanning lines, with comments and trailing commas inside them; plain, single-
and double-quoted scalars, on one line or continued over the lines below;
literal (``|``) and folded (``>``) block scalars with indent and chomping
indicators; full-line and trailing comments; blank lines; ``---``/``...``
document markers.

Error classification is exact, and the three cases never overlap:

* ``UNSUPPORTED_TRANSLATION`` -- well-formed YAML this model cannot reproduce
  faithfully: anchors (``&``), aliases (``*``), tags (``!``), explicit keys
  (``?``), merge keys (``<<``), and a flow collection used as a block mapping
  key. Never a silent flattening.
* ``FORMAT_CONTENT_PARSE_FAILED`` / ``FORMAT_FRAGMENT_PARSE_FAILED`` --
  damaged source: a tab in the indentation, an unterminated quoted scalar or
  flow collection, inconsistent indentation, mapping and sequence entries in
  one block, or a line that is neither an entry nor trivia (which includes a
  bare top-level scalar document, outside this subset). The first code is for
  a whole document, the second for a fragment.
* ``FORMAT_PLUGIN_CONTRACT_ERROR`` -- only a caller passing an argument of the
  wrong type. Never used for anything the source text did.

Every node the plugin produces carries a fresh UUID4 ``node_id`` and a
document-local positive ``short_id`` ({p013}, {p097}).

Source-of-truth requirement labels honored here: {p022}, {p026}, {p049},
{p056}, {p060}, {p062}.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple, Union

from tree_engine.core.nodes import Document, Node
from tree_engine.core.plugin_boundary import FormatBoundary
from tree_engine.exceptions import FormatContentParseFailed, FormatFragmentParseFailed
from tree_engine.plugins.contract import (
    FormatPluginContract, FormatPluginMetadata, SemanticRoleMapping,
)
from tree_engine.plugins.json_pointer import JsonPointerNotation
from tree_engine.plugins.yaml.builder import NodeBuilder
from tree_engine.plugins.yaml.emitter import (
    emit, is_source_tree, node_to_plain, plain_to_node, render,
)
from tree_engine.plugins.yaml.reader import YamlReader
from tree_engine.plugins.yaml.scanner import (
    ENTRY_KINDS, FORMAT_ID, KIND_DOCUMENT, KIND_ITEM, KIND_FLOW_ITEM, KIND_TRIVIA,
    MAPPING_KINDS, PAIR_KINDS, SEQUENCE_KINDS, YamlSyntaxError, contract_error,
)

__all__ = ["FORMAT_ID", "METADATA", "YAML_POINTER", "YamlFormatPlugin", "YAML_FORMAT_PLUGIN"]

METADATA = FormatPluginMetadata(
    format_id=FORMAT_ID,
    aliases=("yml",),
    file_extensions=("yaml", "yml"),
    plugin_version="1.0.0",
    contract_version="1.0.0",
    capabilities={"semantic_role_mapping": True, "byte_identical_round_trip": True},
)

#: YAML models no function, method, class or module construct, so the mapping
#: is empty by design. Callers observe that as ``roles_for(role) == ()`` for
#: every standard role, which is exactly what {p056} asks of a format that
#: does not model them -- not an error and not an omission.
_ROLE_MAP = SemanticRoleMapping({})

#: Entry kinds that carry a sequence position rather than a key.
_ITEM_KINDS = (KIND_ITEM, KIND_FLOW_ITEM)


def _pointer_key(entry: Node) -> Optional[str]:
    """A mapping entry's pointer token: its decoded key, else its raw key text.

    ``decode_scalar`` resolves a key to its YAML value, so ``port: 8080`` gives
    the integer ``8080`` and a JSON Pointer -- whose tokens are strings and
    nothing else -- cannot use it directly. ``key_raw`` is the exact source
    text of the same key, which IS a string and is what a reader of the file
    would type, so it is the fallback. An entry carrying neither has no token
    and no pointer, rather than one invented from its position.
    """

    key = entry.fields.get("key")
    if isinstance(key, str):
        return key
    raw = entry.fields.get("key_raw")
    return raw if isinstance(raw, str) else None


def _pointer_step(parent: Node, child: Node, ordinal: int) -> Optional[Tuple[Tuple[str, ...], bool]]:
    """This format's structural half of RFC 6901, for ``JsonPointerNotation``.

    YAML models comments, blank lines and ``---`` markers as real nodes so a
    document round-trips byte-identically. None of them is a value, and RFC
    6901 addresses values only, so each is refused a pointer instead of being
    given a synthesized one. Block and flow collections are distinct kinds
    carrying identical data, and both are handled by the same clauses here.
    """

    kind, child_kind = parent.kind, child.kind
    if kind == KIND_DOCUMENT:
        # The stream wrapper is not a value; its single value block is what the
        # empty pointer names, so the block claims the root rather than nesting
        # under it.
        return None if child_kind == KIND_TRIVIA else ((), True)
    if kind in MAPPING_KINDS:
        if child_kind not in PAIR_KINDS:
            return None
        key = _pointer_key(child)
        return ((key,), False) if key is not None else None
    if kind in SEQUENCE_KINDS:
        return ((str(ordinal),), False) if child_kind in _ITEM_KINDS else None
    if kind in ENTRY_KINDS:
        # A pair or item is the route to its value, never the value itself.
        return ((), True)
    return None


#: The plugin's reference-notation declaration, read duck-typed by
#: ``tree_engine.core.identifier_map``. ``root_addressable`` is false because
#: ``yaml:Document`` is a stream wrapper: the empty pointer names the value
#: block inside it, which claims that pointer through the step above.
YAML_POINTER = JsonPointerNotation(_pointer_step, root_addressable=False)


class YamlFormatPlugin(FormatPluginContract, FormatBoundary):
    """The registered ``format_id="yaml"`` plugin (concept C-016).

    ``FormatPluginContract`` and ``FormatBoundary`` each declare an abstract
    method named ``parse_document`` (and likewise ``parse_fragment``) with
    different call conventions -- ``(source, options)`` positionally for the
    contract, ``(source, *, source_format_id)`` for the core boundary. The
    signatures below are supersets of both, so one concrete method satisfies
    each name on both bases, exactly as the plain_text and BSL plugins do.
    """

    #: This format's native reference notation ({p021} third correspondence):
    #: JSON Pointer, computed and parsed here rather than by shared code.
    native_reference = YAML_POINTER

    @property
    def metadata(self) -> FormatPluginMetadata:
        """Return this plugin's static identity and capability surface."""

        return METADATA

    def _read(self, source: Union[str, bytes]) -> Tuple[NodeBuilder, List[Node]]:
        """Decode ``source`` and read it, raising the package-private syntax signal.

        Shared by ``parse_document`` and ``parse_fragment`` so both go through
        exactly one reader; each caller maps :class:`YamlSyntaxError` to the
        error code its own stage owns.
        """

        if isinstance(source, (bytes, bytearray)):
            try:
                text = bytes(source).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise YamlSyntaxError(f"cannot decode YAML source as utf-8: {exc}") from exc
        elif isinstance(source, str):
            text = source
        else:
            raise contract_error(
                f"YAML source must be str or bytes, got {type(source).__name__}")
        builder = NodeBuilder()
        return builder, YamlReader(text, builder).read_stream()

    def parse_document(self, source: Union[str, bytes],
                       options: Optional[Mapping[str, Any]] = None, *,
                       source_format_id: Optional[str] = None) -> Document:
        """Parse full YAML source into a common-model ``Document``.

        Damaged source raises ``FormatContentParseFailed``
        (``ErrorCode.FORMAT_CONTENT_PARSE_FAILED``), the code that authorizes
        the plain-text fallback per {p023}. Well-formed YAML that this model
        cannot reproduce raises ``UnsupportedTranslation`` instead, and that
        distinction is deliberate: only the first justifies falling back.
        """

        try:
            builder, children = self._read(source)
        except YamlSyntaxError as exc:
            raise FormatContentParseFailed(f"cannot parse YAML document: {exc}",
                                           plugin_id=FORMAT_ID) from exc
        root = builder.node(KIND_DOCUMENT, {}, children)
        return Document(root=root, source_format_id=FORMAT_ID)

    def parse_fragment(self, fragment: Union[str, bytes],
                       options: Optional[Mapping[str, Any]] = None, *,
                       source_format_id: Optional[str] = None) -> Node:
        """Parse one YAML fragment into a single common-model ``Node``.

        Damaged fragment text raises ``FormatFragmentParseFailed``
        (``ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED``), the fragment-scoped
        counterpart of the document code, so a caller can tell which stage
        failed. A fragment holding one block gets that block; one holding
        several gets a document node wrapping them.
        """

        try:
            builder, children = self._read(fragment)
        except YamlSyntaxError as exc:
            raise FormatFragmentParseFailed(f"cannot parse YAML fragment: {exc}",
                                            plugin_id=FORMAT_ID) from exc
        if len(children) == 1:
            return children[0]
        return builder.node(KIND_DOCUMENT, {}, children)

    def import_external_tree(self, external_tree: Any,
                             options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        """Translate an external YAML representation through the shared importer."""

        return self.import_to_common(external_tree, options)

    def import_to_common(self, external_representation: Any,
                         options: Optional[Mapping[str, Any]] = None) -> Union[Node, Document]:
        """The single input translator shared by every stage ({p056}, {p057}).

        Accepts YAML source text or bytes, which it reads here, or an
        already-decoded plain Python value, which it converts to raw-less
        nodes; common-model input passes through unchanged. The result is
        always common-model nodes, never an internal representation.
        """

        if isinstance(external_representation, (Node, Document)):
            return external_representation
        if isinstance(external_representation, (str, bytes, bytearray)):
            return self.parse_document(external_representation, options)
        return plain_to_node(NodeBuilder(), external_representation, frozenset())

    def export_from_common(self, nodes: Union[Node, Document],
                           options: Optional[Mapping[str, Any]] = None) -> Any:
        """Translate common-model nodes into plain YAML-compatible Python data."""

        root = nodes.root if isinstance(nodes, Document) else nodes
        if not isinstance(root, Node):
            raise contract_error(f"expected a Node or Document, got {type(nodes).__name__}")
        return node_to_plain(root)

    def generate_output(self, target: Union[Node, Document, Any],
                        options: Optional[Mapping[str, Any]] = None) -> Union[str, bytes]:
        """Produce the final YAML text, or bytes when ``options['as_bytes']`` is set.

        A tree that still carries its parsed source text is replayed verbatim,
        which is what makes the document round trip byte for byte; a tree built
        from plain values, and a plain value handed in directly, are written in
        the deterministic canonical style instead.
        """

        options = options or {}
        if isinstance(target, (Node, Document)):
            root = target.root if isinstance(target, Document) else target
            text = render(root) if is_source_tree(root) else emit(node_to_plain(root), 0)
        elif isinstance(target, (dict, list, tuple, str, int, float, bool)) or target is None:
            text = emit(target, 0)
        else:
            raise contract_error(f"cannot generate output for {type(target).__name__}")
        return text.encode("utf-8") if options.get("as_bytes") else text

    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """Return the declarative kind-to-role table: empty for YAML ({p056})."""

        return _ROLE_MAP

    # -- FormatBoundary ----------------------------------------------------

    def render_document(self, document: Document) -> bytes:
        """Render a whole ``Document`` back to source bytes, byte-identically."""

        result = self.generate_output(document, {"as_bytes": True})
        if not isinstance(result, bytes):
            raise contract_error(f"render_document expected bytes, got {type(result).__name__}")
        return result

    def render_fragment(self, node: Node) -> str:
        """Render a single fragment ``Node`` back to source text."""

        result = self.generate_output(node, {})
        if not isinstance(result, str):
            raise contract_error(f"render_fragment expected str, got {type(result).__name__}")
        return result


#: Ready-made stateless singleton, the same registration shape the plain_text,
#: JSON, TOML, Python and BSL plugins expose.
YAML_FORMAT_PLUGIN = YamlFormatPlugin()
