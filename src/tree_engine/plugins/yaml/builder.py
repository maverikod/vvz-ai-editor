"""Node construction for the YAML plugin (concept C-016, step G-023/T-001/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the single place in this package where a common-model ``Node`` is
created, so the identity rule holds everywhere by construction rather than by
each call site remembering it. Per {p013} every node gets a fresh UUID4
``node_id``; per {p097} it also gets a document-local, monotonic, positive
``short_id`` from one :class:`ShortIdMap` per read.

Nothing here knows YAML: it is pure node plumbing shared by the reader and the
emitter.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Node, make_node
from tree_engine.core.short_id import ShortIdMap

__all__ = ["NodeBuilder"]


class NodeBuilder:
    """Builds schema-validated nodes carrying a UUID4 ``node_id`` and a ``short_id``.

    ``make_node`` performs the schema validation, and the validated result is
    then rebuilt through ``Node`` directly so the identity produced here can be
    attached -- the "attach an identity produced elsewhere" pattern that
    ``core/nodes.py`` documents for its ``make_node``/direct-``Node`` split.

    One builder serves one document: the short-id counter it owns is
    document-local, which is exactly the scope {p097} defines for short ids.
    """

    def __init__(self) -> None:
        self.short_ids = ShortIdMap()

    def node(self, kind: str, fields: Optional[Mapping[str, Any]] = None,
             children: Sequence[Node] = ()) -> Node:
        """Return a validated ``Node`` of ``kind`` carrying a fresh identity."""

        valid = make_node(kind, dict(fields or {}), list(children))
        node_id = generate_node_id()
        return Node(kind=valid.kind, fields=valid.fields, children=valid.children,
                    node_id=node_id, short_id=self.short_ids.allocate(node_id))
