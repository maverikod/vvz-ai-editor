#!/usr/bin/env python3
"""Full-cycle documentation example for the ``tree_engine`` package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

This is the runnable story of the whole engine, told mostly through its one
public entry point, ``tree_engine.facade``: load a JSON config, query it,
inspect it, hit a typed error, apply a batch of real mutations, and save.

The facade owns the paired source+tree-file lifecycle itself now:
``facade.open_file`` takes the checksum open decision and reports which
branch it took, and ``facade.write`` publishes both files and reports every
path it wrote. Two stages still drop one layer down, to
``tree_engine.storage.lifecycle.StorageLifecycle``, for the parts the facade
does not surface: session baselines with dual-SHA conflict detection plus a
named overwrite policy and the forced reparse, and the plain-text fallback
seen from the storage side. Each such stage says so in a comment.

Two real engine findings surfaced while writing this example, both worth
knowing about if you build on this code:

* ``StorageLifecycle`` used to never reach the plain-text fallback for a
  plugin that raises the already-typed ``tree_engine.exceptions
  .FormatContentParseFailed`` directly (json/toml/yaml all do this; python
  and bsl instead raise the untyped, plugin-contract-layer carrier, which
  worked). This was fixed in ``lifecycle.py``'s ``_parse`` while this
  example was being written; stage 8 below is the regression proof, on the
  exact family that was broken.
* ``facade.set_attribute`` does not invalidate a node's cached source slice
  the way ``insert``/``delete``/``replace`` do (they route through the
  facade's shared ``_committed`` helper; ``set_attribute`` and
  ``replace_node_id`` do not). For a JSON/BSL node that still carries its
  parse-time cache, the edit is applied to ``fields`` but silently does not
  show up in rendered output. Stage 6 below demonstrates this exactly as
  found and works around it with the one public function that already owns
  cache invalidation, ``core.live_tree.invalidate_cached_source`` -- not a
  facade call, but the smallest fix available without editing the facade.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tree_engine import facade
from tree_engine.core.identity import generate_node_id
from tree_engine.core.live_tree import invalidate_cached_source
from tree_engine.core.nodes import walk
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (ConcurrentSourceModification, FormatFragmentParseFailed,
                                    InvalidParentType)
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.storage.lifecycle import StorageLifecycle
from tree_engine.storage.session_guard import ConflictResolutionPolicy

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

BROKEN_JSON = b'{"service": "billing", "network": {"host": "localhost", '  # truncated, invalid JSON


def _banner(title: str) -> None:
    print(f"\n=== {title} ===")


def _member_id(document, key: str):
    """The node_id of the ``json:Member`` whose own ``key`` field is ``key``,
    found via a real facade selector query -- the same query stage 3 uses,
    reused here as the addressing tool for every later mutation."""
    matches = facade.query(document, f"Member:*[key='{key}']")
    if len(matches) != 1:
        raise LookupError(f"expected exactly one member named {key!r}, found {len(matches)}")
    return matches[0].node_id


def _value_id(document, key: str):
    """The node_id of that member's own value. ``TreeDocument.nodes_by_id``
    and a ``LiveNode``'s ``children`` are themselves facade-returned public
    state (``TreeDocument`` is exported by the facade); there is no facade
    call for "the Nth child of a node", so this one small step reads them
    directly instead of re-implementing a walk."""
    return document.nodes_by_id[_member_id(document, key)].children[0].node_id


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="tree_engine_full_cycle_") as tmp:
        workdir = Path(tmp)
        config_path = workdir / "service_config.json"
        config_path.write_bytes(INITIAL_CONFIG)

        # -- 1. What the facade already knows how to read --
        _banner("1. list_formats(): every built-in format plugin")
        formats = facade.list_formats()
        print(f"registered formats: {sorted(formats)}")
        assert set(formats) == {"python", "bsl", "json", "toml", "yaml", "plain_text"}

        # -- 2. Load, and prove the untouched round trip is byte-identical --
        _banner("2. Load a source file and verify the byte-identical round trip")
        doc = facade.load(config_path)
        print(f"loaded {config_path.name}: format_id={doc.format_id!r}, "
              f"document_version={doc.document_version}")
        assert doc.format_id == "json"
        assert facade.dumps(doc) == INITIAL_CONFIG, "byte-identical round trip failed"
        print("round trip verified: dumps(load(source)) == source, byte for byte")

        # -- 3. Query with a selector --
        _banner("3. Query the tree with a selector")
        # JSON kinds are namespaced ("json:Member") and selector NAMEs cannot
        # contain ':', so a literal kind is matched through the ":*" suffix
        # wildcard the parser already supports, not by spelling the kind out.
        matches = facade.query(doc, "Member:*[key='timeout_seconds']")
        assert len(matches) == 1 and matches[0].type == "json:Member"
        print(f"query \"Member:*[key='timeout_seconds']\" -> one match, type={matches[0].type!r}")
        assert doc.nodes_by_id[matches[0].node_id].children[0].fields["value"] == 30

        # -- 4. Inspect with the compact drill-down view --
        _banner("4. Inspect the document with drill_down")
        outline = facade.drill_down(doc, depth=2)
        for entry in outline.nodes:
            # A deep/large subtree may arrive as a stub instead of a full
            # record: same type/child_count, no depth or name_or_value.
            depth = getattr(entry, "depth", "-")
            label = getattr(entry, "name_or_value", "<collapsed>")
            print(f"  depth={depth} type={entry.type} name/value={label!r} children={entry.child_count}")
        assert outline.nodes[0].type == "json:Object" and outline.nodes[0].depth == 0

        # -- 5. A typed engine error --
        _banner("5. Handle a typed engine error")
        timeout_id = _value_id(doc, "timeout_seconds")
        try:
            facade.set_attribute(doc, timeout_id, "value", object(), expected_version=doc.document_version)
        except InvalidParentType as exc:
            assert exc.code == ErrorCode.INVALID_PARENT_TYPE
            print(f"caught InvalidParentType as expected: code={exc.code.value}")
        else:
            raise AssertionError("expected InvalidParentType was not raised")

        # -- 6. A batch of real mutations, each a version-checked facade call --
        _banner("6. Apply a batch of mutations through the facade")
        # facade.py has no single bulk-apply entry point; each call below is
        # its own atomic, locked, version-checked operation. Chaining them by
        # document_version, back to back, before one save() is this example's
        # "batch": a deliberate sequence, never interleaved with anything else.

        # (boundary, not a bug) a bare "key": value fragment is not a JSON
        # *value*, so JsonFormatPlugin.parse_fragment cannot recognize it; it
        # falls through to the documented "no structure" string result, which
        # facade.insert then refuses rather than insert as a stray node.
        try:
            facade.insert(doc, '"region": "us-east-1"', position="last_child",
                          parent=doc.root.node_id, expected_version=doc.document_version)
        except FormatFragmentParseFailed as exc:
            assert exc.code == ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED
            print(f"insert of a bare member fragment refused as expected: {exc}")
        else:
            raise AssertionError("expected FormatFragmentParseFailed was not raised")

        # (a) insert: append a new item into the "features" array -- an
        # array's children ARE its body, no Member wrapper needed, so this
        # (unlike the attempt above) is fully expressible.
        facade.insert(doc, '"audit"', position="last_child", parent=_value_id(doc, "features"),
                      expected_version=doc.document_version)

        # (b) delete: drop "retries_enabled" entirely.
        facade.delete(doc, _member_id(doc, "retries_enabled"), expected_version=doc.document_version)

        # (c) replace: swap the whole "network" object for a smaller one --
        # mints a brand-new node identity for the replaced subtree.
        facade.replace(doc, _value_id(doc, "network"), '{"host": "localhost", "port": 9090}',
                       expected_version=doc.document_version)

        # (d) attribute mutation, in place -- same node_id/short_id throughout.
        service_id = _value_id(doc, "service")
        facade.set_attribute(doc, service_id, "value", "billing-v2", expected_version=doc.document_version)
        # Known gap (see module docstring): set_attribute does not clear the
        # stale cached-source field JSON left on this node at parse time, so
        # without this call the edit above would be silently unrendered.
        invalidate_cached_source(doc.nodes_by_id[service_id])

        # (e) bare identifier reassignment on that SAME node: content already
        # changed above without touching identity; now identity changes
        # without touching content -- the two are orthogonal primitives.
        new_service_node_id = generate_node_id()
        facade.replace_node_id(doc, service_id, new_service_node_id, expected_version=doc.document_version)

        final = json.loads(facade.dumps(doc))
        assert final == {"service": "billing-v2", "network": {"host": "localhost", "port": 9090},
                         "features": ["metrics", "tracing", "audit"]}
        assert doc.nodes_by_id[new_service_node_id].fields["value"] == "billing-v2"
        print(f"batch applied, document_version={doc.document_version}, final content: {final}")

        written = facade.write(doc, path=config_path)
        print(f"saved via facade.write(): {config_path.read_bytes()}")
        # facade.write() publishes the PAIR -- the source file and the tree
        # file beside it -- and reports every path it wrote, which is what a
        # caller owning atomicity elsewhere needs in order to stage them.
        assert written.written_paths == (config_path, written.tree_path)
        print(f"paths written: {[p.name for p in written.written_paths]}")
        # Because that tree file carries every node_id/short_id, reopening the
        # same bytes takes the checksum-match branch and identity survives.
        reopened_by_facade = facade.open_file(config_path)
        assert reopened_by_facade.branch is facade.OpenBranch.SHA_MATCH
        assert reopened_by_facade.identity_preserved is True
        assert reopened_by_facade.tree_write_intent is facade.TreeWriteIntent.NONE
        assert new_service_node_id in reopened_by_facade.document.nodes_by_id
        print(f"reopened by the facade: branch={reopened_by_facade.branch.value}, "
              f"identity_preserved={reopened_by_facade.identity_preserved}")

        # -- 7. Storage-layer pairing: identity round trip, conflict, recovery --
        _banner("7. StorageLifecycle: paired storage, identity round trip, conflict")
        # The facade drives StorageLifecycle for exactly the open decision and
        # the paired write. The layer below is still the place for the pieces
        # the facade does not surface -- the session baselines, the named
        # overwrite policy, the forced reparse -- and is used directly here.
        # It runs on its own copy of the document so the pair the facade just
        # published above stays untouched by this walkthrough.
        paired_path = workdir / "paired_config.json"
        paired_path.write_bytes(config_path.read_bytes())
        registry = FormatPluginRegistry()
        registry.register_format_plugin(JSON_FORMAT_PLUGIN)
        registry.register_format_plugin(PLAIN_TEXT_FORMAT_PLUGIN)
        lifecycle = StorageLifecycle(registry)
        plugin = registry.get_format_plugin("json")

        # First open: no tree file exists beside this copy yet, so this is
        # necessarily a full rebuild from source text, minting fresh node
        # identities -- exactly what facade.open_file() reports as NO_SIDECAR.
        opened = lifecycle.open(paired_path)
        assert opened.rebuilt is True
        assert plugin.render_document(opened.document) == paired_path.read_bytes()
        some_id = opened.document.root.children[0].children[0].node_id  # the "service" value node

        # This save publishes the sidecar tree file, which encodes every
        # node's exact node_id/short_id -- never reallocating one.
        saved = lifecycle.save(opened, document=opened.document)
        assert saved.tree_path.exists()

        # Second open: the sidecar is valid and matches the source, so it is
        # decoded and accepted rather than rebuilt -- this is the genuine
        # identity round trip.
        reopened = lifecycle.open(paired_path)
        assert reopened.rebuilt is False
        assert some_id in {n.node_id for n in walk(reopened.document.root)}, \
            "node identity must survive a real open()-after-save() round trip"
        print("identity verified: the same node_id survived a paired storage save/reload")

        # A conflicting external write, refused then explicitly resolved.
        paired_path.write_bytes(b'{"note": "written by someone else while we were editing"}\n')
        try:
            lifecycle.save(reopened, document=reopened.document)
        except ConcurrentSourceModification as exc:
            assert exc.code == ErrorCode.CONCURRENT_SOURCE_MODIFICATION
            print(f"save refused as expected: code={exc.code.value}")
        else:
            raise AssertionError("expected ConcurrentSourceModification was not raised")
        resolved = lifecycle.save(reopened, document=reopened.document,
                                  policy=ConflictResolutionPolicy.OVERWRITE_SOURCE)
        print("retried with policy=OVERWRITE_SOURCE: the concurrent write was intentionally discarded")
        assert some_id in {n.node_id for n in walk(resolved.document.root)}

        # Contrast: reparse() forces a full rebuild from the current source
        # text even over a valid sidecar, so -- unlike an ordinary open() --
        # it does NOT preserve identity. Worth knowing, not a bug.
        reparsed = lifecycle.reparse(paired_path)
        assert reparsed.rebuilt is True
        assert some_id not in {n.node_id for n in walk(reparsed.document.root)}
        print("reparse() confirmed to discard identity: it re-derives from source text, on purpose")

        # -- 8. Unparseable input degrades to the plain-text fallback --
        _banner("8. Unparseable JSON degrades to the plain-text fallback (regression proof)")
        broken_path = workdir / "broken.json"
        broken_path.write_bytes(BROKEN_JSON)
        fallback_opened = lifecycle.open(broken_path)
        assert fallback_opened.fallback is True
        assert fallback_opened.document.source_format_id == "json"
        assert fallback_opened.document.representation_format_id == "plain_text"
        fallback_plugin = registry.get_format_plugin(fallback_opened.document.format_id)
        assert fallback_plugin.render_document(fallback_opened.document) == BROKEN_JSON
        assert broken_path.read_bytes() == BROKEN_JSON, "source bytes must be untouched by a failed parse"
        print("fallback verified: malformed JSON opened as plain_text with every byte intact")

        print("\nALL STAGES PASSED")


if __name__ == "__main__":
    main()
