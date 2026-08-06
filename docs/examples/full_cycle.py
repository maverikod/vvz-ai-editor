#!/usr/bin/env python3
"""Full-cycle documentation example for the ``tree_engine`` package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

This is the runnable story of the whole engine, told through the lowest
layer that is actually merged today: ``tree_engine.storage.lifecycle
.StorageLifecycle`` (open/save/reparse of one source+tree file pair),
``tree_engine.query`` (selector search and compact inspection), and the
immutable ``tree_engine.core.nodes.Node``/``Document`` model that every
format plugin produces and every mutation rebuilds.

Why not the public facade? ``tree_engine.facade`` is being written by a
parallel step and is not merged in this worktree, so it is not imported or
stubbed here. Two consequences worth knowing about, reported in full at the
bottom of this docstring's companion step report:

* ``tree_engine.core.operations``/``updates`` (``insert``/``delete``/
  ``set_attribute``/``set_body`` as free functions) are written against a
  duck-typed *mutable, indexed* document -- a settable ``node.children``
  and a live ``document.nodes_by_id``/``short_id_index`` -- that neither a
  format plugin nor ``StorageLifecycle`` builds today. That indexed, live
  session is exactly what the facade is expected to supply. Until then,
  editing a real parsed document means working with what ``core.nodes``
  actually gives you: an immutable ``Node`` (frozen dataclass, tuple
  ``children``) rebuilt bottom-up via ``dataclasses.replace`` -- which is
  what this example does, with one small local helper, ``_rebuild``, doing
  the bottom-up splice. Every operation below is still a real engine
  concept -- insert, delete, replace, attribute mutation, identifier
  reassignment -- just expressed at the level the merged code offers.
* A ``TreeQueryEngine`` match (``QueryMatch``) is intentionally a compact
  address record (``node_id``/``short_id``/type/name), not a live node
  reference -- so this example resolves a match back to the actual
  ``Node`` object via ``tree_engine.core.nodes.walk``, exactly as any
  caller must until a facade-level "resolve a match to its node" helper
  exists.

The story, in order: open a JSON config file through the storage
lifecycle; prove the untouched round trip is byte-identical; query it with
a selector; inspect it with the compact drill-down view; see a typed
engine error; apply a batch of five real mutations (insert, delete,
replace, an attribute-only edit, and a bare identifier reassignment) in
one atomic save; reload and prove both the new content and node identity
survived; hit and resolve a concurrent-write conflict on save; and finally
open a syntactically broken file and watch it degrade to the plain-text
fallback without losing a single byte.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import tempfile
from pathlib import Path
from typing import Callable, Optional

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Node, NodeSchemaError, make_node, walk
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import ConcurrentSourceModification
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.query.engine import TreeQueryEngine
from tree_engine.query.inspection import drill_down
from tree_engine.storage.lifecycle import StorageLifecycle
from tree_engine.storage.session_guard import ConflictResolutionPolicy

# The real "json:*" kind strings JsonFormatPlugin builds and consumes
# (tree_engine.plugins.json_format.KIND_*, mirrored here since that module
# exports only the plugin class and singleton through __all__).
JSON_OBJECT, JSON_MEMBER, JSON_ARRAY, JSON_STRING, JSON_NUMBER = (
    "json:Object", "json:Member", "json:Array", "json:String", "json:Number",
)

INITIAL_CONFIG = (
    b'{\n'
    b'  "service": "billing",\n'
    b'  "network": {\n'
    b'    "host": "localhost",\n'
    b'    "port": 8080,\n'
    b'    "timeout_seconds": 30\n'
    b'  },\n'
    b'  "features": ["metrics", "tracing"],\n'
    b'  "retries_enabled": true\n'
    b'}\n'
)

BROKEN_SOURCE = b"def broken(:\n    pass\n"  # invalid Python syntax, on purpose


def _banner(title: str) -> None:
    print(f"\n=== {title} ===")


def _max_short_id(root: Node) -> int:
    """Highest short_id already used anywhere in ``root``'s subtree, so a
    freshly minted one is guaranteed not to collide with it ({p097})."""
    return max((n.short_id for n in walk(root) if isinstance(n.short_id, int)), default=0)


def _new_node(kind: str, fields: dict, children: tuple, short_ids: "itertools.count[int]") -> Node:
    """Build one brand-new, identified ``Node``: shape-validated by
    ``make_node``, then given a fresh UUID4 node_id and the next unused
    short_id -- the same two-step every format plugin already follows."""
    built = make_node(kind, fields=fields, children=children)
    return dataclasses.replace(built, node_id=generate_node_id(), short_id=next(short_ids))


def _rebuild(root: Node, target_id: object, transform: Callable[[Node], Node]) -> Node:
    """Return a new tree with the node whose node_id is ``target_id``
    replaced by ``transform(node)``. Every ancestor on the path down to it
    is rebuilt with a fresh ``children`` tuple (``Node`` is frozen, so this
    is the only way to change one), and each rebuilt ancestor's stale
    ``"raw"`` byte-cache is dropped -- JsonFormatPlugin's own renderer
    replays a node's ``"raw"`` field verbatim when present, so a container
    whose children changed must lose that cache or the edit stays invisible
    on save. Untouched subtrees are returned completely unchanged (same
    object), which is also how the "nothing changed" safety check below
    detects an unresolvable target_id."""
    if root.node_id == target_id:
        return transform(root)
    if not root.children:
        return root
    new_children = tuple(_rebuild(child, target_id, transform) for child in root.children)
    if new_children == root.children:
        return root
    fields = dict(root.fields)
    fields.pop("raw", None)
    return dataclasses.replace(root, children=new_children, fields=fields)


def rebuild(root: Node, target_id: object, transform: Callable[[Node], Node]) -> Node:
    """``_rebuild`` plus the loud failure this documentation example wants:
    a ``target_id`` that matches nothing must never silently no-op."""
    result = _rebuild(root, target_id, transform)
    if result is root and root.node_id != target_id:
        raise LookupError(f"no node with node_id={target_id!r} found to rebuild")
    return result


def _member(container: Node, key: str) -> Node:
    """The ``json:Member`` direct child of ``container`` whose own ``key``
    field equals ``key`` -- the JSON plugin's own shape (an Object's
    children are Member nodes, each with a ``"key"`` field and one child,
    the value)."""
    for child in container.children:
        if child.kind == JSON_MEMBER and child.fields.get("key") == key:
            return child
    raise LookupError(f"no member named {key!r} under {container.kind}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="tree_engine_full_cycle_") as tmp:
        workdir = Path(tmp)
        config_path = workdir / "service_config.json"
        config_path.write_bytes(INITIAL_CONFIG)

        # Every format plugin this example touches must be registered before
        # StorageLifecycle can resolve a source file to one. PLAIN_TEXT_FORMAT_PLUGIN
        # is mandatory: it is the fallback StorageLifecycle reaches for on a
        # classified parse failure, and get_format_plugin("plain_text") raises
        # FormatPluginNotFound without it.
        registry = FormatPluginRegistry()
        registry.register_format_plugin(JSON_FORMAT_PLUGIN)
        registry.register_format_plugin(PLAIN_TEXT_FORMAT_PLUGIN)
        registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)
        lifecycle = StorageLifecycle(registry)

        # -- 1. Open, and prove the untouched round trip is byte-identical --
        _banner("1. Open a source file through the storage lifecycle")
        opened = lifecycle.open(config_path)
        print(f"opened {opened.source_path.name}: format={opened.format_id!r}, "
              f"rebuilt={opened.rebuilt}, fallback={opened.fallback}, "
              f"document_version={opened.envelope.document_version}")
        assert opened.format_id == "json"
        assert opened.rebuilt is True   # no sidecar .tree.json existed yet
        assert opened.fallback is False
        assert opened.tree_path.exists(), "open() must have published the sidecar tree file"

        plugin = registry.get_format_plugin(opened.document.format_id)
        rendered = plugin.render_document(opened.document)
        assert rendered == INITIAL_CONFIG, "byte-identical round trip failed"
        assert opened.source_sha256 == hashlib.sha256(INITIAL_CONFIG).hexdigest()
        print("round trip verified: render_document(parse_document(source)) == source, byte for byte")

        # -- 2. Query with a selector --
        _banner("2. Query the tree with a selector")
        engine = TreeQueryEngine(opened.document, plugin)
        # JSON kinds are namespaced ("json:Member") and selector NAMEs cannot
        # contain ':', so a literal kind is matched through the ":*" suffix
        # wildcard the parser already supports, not by spelling the kind out.
        matches = engine.query("Member:*[key='timeout_seconds']")
        assert len(matches) == 1
        match = matches[0]
        print(f"query \"Member:*[key='timeout_seconds']\" -> one match, type={match.type!r}")
        by_id = {node.node_id: node for node in walk(opened.document.root)}
        timeout_member = by_id[match.node_id]
        assert timeout_member.fields["key"] == "timeout_seconds"
        assert timeout_member.children[0].fields["value"] == 30

        # -- 3. Inspect with the compact drill-down view --
        _banner("3. Inspect the document with drill_down")
        outline = drill_down(opened.document, address=None, depth=2)
        for entry in outline.nodes:
            # A deep/large subtree may arrive as an OutlineStubRecord instead
            # of a full OutlineNodeRecord: same type/child_count, no depth or
            # name_or_value, per {p071} -- handled generically here.
            depth = getattr(entry, "depth", "-")
            label = getattr(entry, "name_or_value", "<collapsed>")
            print(f"  depth={depth} type={entry.type} name/value={label!r} "
                  f"children={entry.child_count}")
        assert outline.nodes[0].type == JSON_OBJECT
        assert outline.nodes[0].depth == 0

        # -- 4. A typed engine error --
        _banner("4. Handle a typed engine error")
        try:
            make_node(JSON_STRING, fields={"value": object()})  # not a valid FieldValue
        except NodeSchemaError as exc:
            assert exc.code == ErrorCode.INVALID_PARENT_TYPE
            print(f"caught NodeSchemaError as expected: code={exc.code.value}")
        else:
            raise AssertionError("expected NodeSchemaError was not raised")

        # -- 5. A batch of real mutations, applied and saved atomically --
        _banner("5. Apply a batch of mutations, then save once")
        root = opened.document.root
        short_ids = itertools.count(_max_short_id(root) + 1)

        # (a) insert: a brand-new "region" member, right after "service".
        def _insert_region(obj: Node) -> Node:
            value = _new_node(JSON_STRING, {"value": "us-east-1"}, (), short_ids)
            member = _new_node(JSON_MEMBER, {"key": "region"}, (value,), short_ids)
            children = list(obj.children)
            index = next(i for i, c in enumerate(children) if c.fields.get("key") == "service") + 1
            children.insert(index, member)
            fields = dict(obj.fields); fields.pop("raw", None)
            return dataclasses.replace(obj, children=tuple(children), fields=fields)

        root = rebuild(root, root.node_id, _insert_region)

        # (b) delete: drop "retries_enabled" entirely.
        def _delete_retries(obj: Node) -> Node:
            children = tuple(c for c in obj.children if c.fields.get("key") != "retries_enabled")
            fields = dict(obj.fields); fields.pop("raw", None)
            return dataclasses.replace(obj, children=children, fields=fields)

        root = rebuild(root, root.node_id, _delete_retries)

        # (c) replace: swap the whole "features" array for a new one. This
        # mints a brand-new node identity for the array, unlike (d) below.
        features_array_id = _member(root, "features").children[0].node_id

        def _replace_features(_old_array: Node) -> Node:
            items = (
                _new_node(JSON_STRING, {"value": "metrics"}, (), short_ids),
                _new_node(JSON_STRING, {"value": "audit"}, (), short_ids),
            )
            return _new_node(JSON_ARRAY, {}, items, short_ids)

        root = rebuild(root, features_array_id, _replace_features)

        # (d) attribute mutation: bump network.port in place -- same node_id
        # and short_id throughout, only the "value" field changes.
        network = _member(root, "network").children[0]
        port_value_id = _member(network, "port").children[0].node_id

        def _bump_port(number: Node) -> Node:
            fields = dict(number.fields); fields["value"] = 9090; fields.pop("raw", None)
            return dataclasses.replace(number, fields=fields)

        root = rebuild(root, port_value_id, _bump_port)

        # (e) bare identifier reassignment: give network.host a new node_id,
        # content and short_id both left alone -- the inverse contrast of (d).
        host_value_id = _member(network, "host").children[0].node_id
        new_host_node_id = generate_node_id()
        root = rebuild(root, host_value_id, lambda node: dataclasses.replace(node, node_id=new_host_node_id))

        edited_document = dataclasses.replace(opened.document, root=root)
        saved = lifecycle.save(opened, document=edited_document)
        print(f"saved: document_version={saved.envelope.document_version}, rebuilt={saved.rebuilt}")
        assert saved.rebuilt is False

        # -- 6. Reload and prove content AND identity survived --
        _banner("6. Reload from disk and verify persistence")
        reloaded = lifecycle.open(config_path)
        r_root = reloaded.document.root
        assert _member(r_root, "region").children[0].fields["value"] == "us-east-1"
        assert all(c.fields.get("key") != "retries_enabled" for c in r_root.children)
        r_network = _member(r_root, "network").children[0]
        assert _member(r_network, "port").children[0].fields["value"] == 9090
        r_host_value = _member(r_network, "host").children[0]
        assert r_host_value.node_id == new_host_node_id, "node identity did not survive save/reload"
        r_features = _member(r_root, "features").children[0]
        assert [c.fields["value"] for c in r_features.children] == ["metrics", "audit"]
        reloaded_plugin = registry.get_format_plugin(reloaded.document.format_id)
        assert reloaded_plugin.render_document(reloaded.document) == config_path.read_bytes()
        print("reload verified: edited content is correct and network.host kept its exact node_id")

        # -- 7. A conflicting external write, refused then resolved --
        _banner("7. Conflict on save: refuse, then explicitly overwrite")
        r_root2 = rebuild(r_root, port_value_id, lambda n: dataclasses.replace(
            n, fields={**{k: v for k, v in n.fields.items() if k != "raw"}, "value": 9091}))
        second_edit = dataclasses.replace(reloaded.document, root=r_root2)
        config_path.write_bytes(b'{"note": "written by someone else while we were editing"}\n')
        try:
            lifecycle.save(reloaded, document=second_edit)
        except ConcurrentSourceModification as exc:
            assert exc.code == ErrorCode.CONCURRENT_SOURCE_MODIFICATION
            print(f"save refused as expected: code={exc.code.value}")
        else:
            raise AssertionError("expected ConcurrentSourceModification was not raised")
        resolved = lifecycle.save(reloaded, document=second_edit, policy=ConflictResolutionPolicy.OVERWRITE_SOURCE)
        print("retried with policy=OVERWRITE_SOURCE: the concurrent write was intentionally discarded")
        r_root3 = resolved.document.root
        assert _member(_member(r_root3, "network").children[0], "port").children[0].fields["value"] == 9091

        # -- 8. An unparseable file degrades to the plain-text fallback --
        _banner("8. Unparseable input degrades to the plain-text fallback")
        # Python, not JSON, on purpose: a plugin's parse failure only reaches
        # StorageLifecycle's fallback branch when it is raised as the
        # plugin-contract-layer FormatPluginContractError (untyped, carrying
        # .error_code) -- exactly what PythonFormatPlugin raises. JsonFormatPlugin
        # instead raises the already-typed tree_engine.exceptions.FormatContentParseFailed
        # directly, which StorageLifecycle's own "already typed -> re-raise
        # unchanged" rule (by design, for errors it must never reinterpret)
        # propagates straight to the caller instead of falling back -- a real,
        # reportable gap between the two plugins' failure classification, not
        # a fallback-mechanism bug in general.
        broken_path = workdir / "broken.py"
        broken_path.write_bytes(BROKEN_SOURCE)
        fallback_opened = lifecycle.open(broken_path)
        assert fallback_opened.fallback is True
        assert fallback_opened.document.source_format_id == "python"
        assert fallback_opened.document.representation_format_id == "plain_text"
        fallback_plugin = registry.get_format_plugin(fallback_opened.document.format_id)
        assert fallback_plugin.render_document(fallback_opened.document) == BROKEN_SOURCE
        assert broken_path.read_bytes() == BROKEN_SOURCE, "source bytes must be untouched by a failed parse"
        print("fallback verified: malformed Python opened as plain_text with every byte intact")

        print("\nALL STAGES PASSED")


if __name__ == "__main__":
    main()
