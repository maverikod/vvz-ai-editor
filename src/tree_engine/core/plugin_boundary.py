"""CORE-side translation boundary for format plugins (concept C-002).

Scope: this module defines the abstract contract a format plugin must
satisfy to exchange common-model trees with the core, per HRS {p045}. It
does not define plugin registration, discovery, or lookup -- that is G-004's
scope -- and it contains no registry. It also does not implement, select, or
construct any concrete plugin.

Isolation invariant ({p045}): the core -- including this file -- must never
import, type-hint, or otherwise reference a specific external parser/codegen
library's classes (e.g. LibCST, ``ast``, tree-sitter, ...). Every method
signature below is typed using only common-model types
(:class:`~tree_engine.core.nodes.Node`, :class:`~tree_engine.core.nodes.Document`)
or primitives (``bytes``, ``str``). An external library's tree object may be
imported and used only inside a concrete plugin module that implements
:class:`FormatBoundary`, and only within the bodies of that plugin's own
methods -- never at this module's level and never in any signature defined
here. A plugin implementation must never let an external library object
escape across this boundary: every value returned to a caller through
:class:`FormatBoundary` must be a common-model type or a primitive.

Error attribution: this file documents, via each method's docstring, which
stable :class:`~tree_engine.errors.ErrorCode` (see
``src/tree_engine/errors.py``) is the expected failure signal for that
method. It does not define, invent, or duplicate any error code, and it
defines no exception classes -- the typed exception hierarchy built on the
catalog is delivered later by the public-facade step tied to concept C-021.

Conformance: :func:`implements_format_boundary` is the one small,
unit-testable helper this module provides so a test can assert that a
candidate plugin class (or instance) structurally satisfies
:class:`FormatBoundary`, without that candidate needing to subclass anything
defined here.
"""

from __future__ import annotations

import abc
from typing import Any

from tree_engine.core.nodes import Document, Node

__all__ = [
    "FormatBoundary",
    "implements_format_boundary",
]


class FormatBoundary(abc.ABC):
    """Abstract CORE-side boundary every format plugin must implement.

    Only common-model types (:class:`Document`, :class:`Node`) or
    primitives (``bytes``, ``str``) appear in these method signatures; no
    external parser/codegen library type may appear as a parameter or
    return type anywhere on this interface. A concrete implementation lives
    entirely inside a plugin module: it may import and use any external
    library it needs within its method bodies, but must translate to and
    from common-model types at this boundary so no external library object
    is ever visible to a caller of this interface.

    No plugin registration, discovery, or lookup is defined or implied here
    (reserved for G-004); this class only describes the shape a single
    plugin must expose once it has already been resolved by whatever
    mechanism a later step provides.
    """

    @abc.abstractmethod
    def parse_document(self, source: bytes, *, source_format_id: str) -> Document:
        """Translate a full source buffer into a common-model ``Document``.

        ``source`` is the raw bytes of an entire source file; the returned
        ``Document`` is the common-model tree, with ``source_format_id``
        (and, ordinarily, an equal ``representation_format_id``) recorded
        per {p050}. This is whole-document parsing, distinct from
        :meth:`parse_fragment`.

        Expected failure signal: a plugin that cannot parse ``source`` as
        valid content of ``source_format_id`` must signal
        ``ErrorCode.FORMAT_CONTENT_PARSE_FAILED``.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def parse_fragment(self, source: str, *, source_format_id: str) -> Node:
        """Translate a partial/fragment source string into a single ``Node``.

        Unlike :meth:`parse_document`, ``source`` need not be a complete,
        standalone document -- this is for incremental edit scenarios where
        only a subtree is being (re)parsed. The result is a single
        common-model ``Node`` subtree.

        Expected failure signal: a plugin that cannot parse ``source`` as a
        recognizable fragment of ``source_format_id`` must signal
        ``ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED``.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def render_document(self, document: Document) -> bytes:
        """Translate a common-model ``Document`` back into source bytes.

        Implementations must preserve byte-for-byte fidelity ({p022}) for
        any subtree of ``document.root`` left untouched since it was
        produced by :meth:`parse_document`.

        Expected failure signal: if a common-model construct in
        ``document`` has no faithful representation in this plugin's
        format, the plugin must signal ``ErrorCode.UNSUPPORTED_TRANSLATION``
        rather than silently dropping or approximating it.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def render_fragment(self, node: Node) -> str:
        """Translate a single common-model ``Node`` back into source text.

        The counterpart of :meth:`parse_fragment`: renders one subtree, not
        a whole document.

        Expected failure signal: if ``node`` (or a construct within it) has
        no faithful representation in this plugin's format, the plugin must
        signal ``ErrorCode.UNSUPPORTED_TRANSLATION``.
        """

        raise NotImplementedError


def implements_format_boundary(candidate: Any) -> bool:
    """Return whether ``candidate`` structurally satisfies :class:`FormatBoundary`.

    ``candidate`` may be a class or an instance. This is the conformance
    helper a test uses to assert that a plugin class satisfies the
    boundary; it performs the same ABC-registration check
    :func:`issubclass`/``isinstance`` would, without requiring the
    candidate to be constructed first when given a class.

    Any violation of this boundary's own calling contract by a *runtime*
    call -- a wrong argument type, an external-library object or ``None``
    returned where a common-model type is required, and so on -- is a
    concern for the plugin's own defensive checks and for the caller that
    invokes it; it is signaled via
    ``ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR`` and is out of scope for this
    static structural check.
    """

    target = candidate if isinstance(candidate, type) else type(candidate)
    return issubclass(target, FormatBoundary)
