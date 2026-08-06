"""API-contract tests for the public facade ``tree_engine.facade`` (G-027/T-001/A-005, C-021).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The facade is the package's single public entry point ({p037}), so the property defended above all
others is IMPORT DISCIPLINE: a caller must load, inspect, mutate, render and save a real document --
and annotate or ``isinstance``-check every result -- through ``tree_engine.facade`` alone, never
reaching into ``tree_engine.core.*``/``tree_engine.plugins.*``.
``test_facade_only_arc_runs_in_a_pristine_interpreter`` enforces that mechanically: a SUBPROCESS
runs a script whose only engine import is the facade, performs a full end-to-end arc, then asserts
no other engine module ended up bound. The plugin AUTHOR case is separate -- declaring a format
needs ``plugins.contract`` for one value type -- while the plugin USER stays on the facade.

Everything runs against the real merged engine, the real six built-in plugins and real files; no
part of the engine is mocked and ``_KeyValuePlugin`` really parses and renders its own syntax. Also
covered: the built-ins are registered ({p055}); untouched documents round-trip byte-identically in
memory and on disk; an unparsable source degrades to the one authorized plain-text fallback and
still renders the ORIGINAL BYTES ({p058}); every reachable failure is typed with a real
``ErrorCode`` and layer ({p023}); every {j9rh} address form resolves and every bad one is rejected
first; a stale ``expected_version`` changes nothing ({p024}); each mutating entry point changes the
render; and the two documented limits fail typed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, List
from uuid import uuid4

import pytest

from tree_engine import facade
from tree_engine.errors import ErrorCode, ErrorLayer
from tree_engine.exceptions import TreeEngineException
from tree_engine.plugins.contract import FormatPluginMetadata  # plugin-author import, see docstring

BUILT_INS = ("python", "bsl", "json", "toml", "yaml", "plain_text")
PYTHON = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
JSON = '{\n  "a": 1,\n  "b": 2\n}\n'
BROKEN_PYTHON = "def broken(:\n    ???\n"

SAMPLES = (("python", PYTHON, ".py"),
           ("bsl", 'Procedure Test()\n    Message("x");\nEndProcedure\n', ".bsl"),
           ("json", JSON, ".json"),
           ("toml", 'title = "x"\n\n[owner]\nname = "y"\n', ".toml"),
           ("yaml", "a: 1\nb:\n  - 1\n  - 2\n", ".yaml"))

FACADE_ONLY_ARC = '''
import sys
from types import ModuleType

import tree_engine.facade as facade

ENTRY_POINTS = ("load", "save", "loads", "dumps", "reparse", "query", "drill_down", "insert",
                "delete", "replace", "move", "copy_subtree", "apply_subtree", "set_attribute",
                "set_body", "replace_node_id", "resolve_address", "register_format_plugin",
                "list_formats")
workdir, source, out = sys.argv[1], '{"a": 1, "b": 2}', sys.argv[1] + "/out.json"
assert all(callable(getattr(facade, name)) for name in ENTRY_POINTS)
assert set(ENTRY_POINTS) <= set(facade.__all__)
assert facade.list_formats() == ("python", "bsl", "json", "toml", "yaml", "plain_text")
open(workdir + "/doc.json", "w", encoding="utf-8").write(source)
doc = facade.load(workdir + "/doc.json")
member = doc.root.children[0]
assert isinstance(doc, facade.TreeDocument) and facade.dumps(doc) == source.encode()
assert isinstance(facade.drill_down(doc, depth=2), facade.OutlineResponse)
assert isinstance(facade.query(doc, "*")[0], facade.QueryMatch)
assert facade.resolve_address(doc, member.short_id) == member.node_id
assert isinstance(facade.move(doc, member.short_id, position="last_child",
                              parent=doc.root.short_id), facade.MoveResult)
copied = facade.copy_subtree(doc, doc.root.children[0].short_id)
assert isinstance(copied, facade.CopiedDocument)
assert isinstance(facade.apply_subtree(doc, copied), facade.ApplySubtreeResult)
assert isinstance(facade.delete(doc, doc.root.children[-1].short_id), facade.MutationResult)
assert isinstance(facade.set_attribute(doc, doc.root.children[0].short_id, "key", "renamed"),
                  facade.MutationResult)
assert str(facade.save(doc, out)) == out
assert facade.dumps(facade.load(out)) == facade.dumps(doc) == b'{"renamed": 2}'
try:
    facade.delete(doc, doc.root.children[0].short_id, expected_version=10 ** 6)
    raise SystemExit("a stale expected_version was accepted")
except Exception as error:
    assert type(error).__module__ == "tree_engine.exceptions", type(error).__module__
    assert error.code.value == "DOCUMENT_VERSION_CONFLICT", error.code
bound = sorted({value.__name__ for value in list(globals().values())
                if isinstance(value, ModuleType) and value.__name__.startswith("tree_engine")})
assert bound == ["tree_engine.facade"], bound
print("FACADE_ONLY_ARC_OK")
'''

KVD_FORMAT_ID, KVD_SOURCE = "kvd_demo", "alpha=1\nbeta=2\n"


def _kvd_node(kind: str, fields: Any, children: Any = ()) -> SimpleNamespace:
    """A node as a third-party plugin builds it: the attribute surface the engine reads."""
    return SimpleNamespace(kind=f"{KVD_FORMAT_ID}:{kind}", fields=fields, children=list(children),
                           node_id=uuid4(), short_id=None, extended_type=None, buffer_range=None,
                           references=())


class _KeyValuePlugin:
    """A real third-party ``key=value`` line format authored against the published plugin contract
    alone: one ``Entry`` per line, in the root's single ``entries`` field so a core splice mirrors
    into it, rendered by concatenation -- which keeps it byte-identical."""

    metadata = FormatPluginMetadata(
        format_id=KVD_FORMAT_ID, aliases=(), file_extensions=("kvd",), plugin_version="1.0.0",
        contract_version="1.0.0", capabilities={"semantic_role_mapping": False})

    def parse_document(self, source: str, options: Any = None) -> SimpleNamespace:
        """Split ``source`` into one ``Entry`` per ``key=value`` line, terminator kept verbatim."""
        root = _kvd_node("Document", {})
        for line in source.splitlines(keepends=True):
            key, separator, value = line.partition("=")
            if not separator:
                raise ValueError(f"line without a key=value separator: {line!r}")
            root.children.append(_kvd_node("Entry", {"key": key, "value": value}))
        root.fields = {"entries": tuple(root.children)}
        return SimpleNamespace(root=root, representation_format_id=KVD_FORMAT_ID)

    def parse_fragment(self, source: str, options: Any = None) -> List[SimpleNamespace]:
        """The same parser, returning the entries themselves for a splice."""
        return self.parse_document(source).root.children

    def generate_output(self, target: Any, options: Any = None) -> str:
        """Concatenate the entries back, in order."""
        root = getattr(target, "root", target)
        return "".join(f"{n.fields['key']}={n.fields['value']}" for n in root.children)


@pytest.fixture
def registered_kvd_plugin() -> Iterator[_KeyValuePlugin]:
    """Register the third-party plugin and take it back out, leaving only the six built-ins."""
    facade.register_format_plugin(_KeyValuePlugin())
    try:
        yield facade._REGISTRY.get_format_plugin(KVD_FORMAT_ID)
    finally:
        facade._REGISTRY.unregister_format_plugin(KVD_FORMAT_ID)
        facade._EXTENSIONS.pop("kvd", None)


def _first(document: facade.TreeDocument, kind: str) -> Any:
    """The first live node of ``kind``, in index order."""
    return next(node for node in document.nodes_by_id.values() if node.kind == kind)


def test_list_formats_returns_every_built_in_plugin() -> None:
    """{p055}: all six shipped format plugins are registered with the facade, in load order."""
    assert facade.list_formats() == BUILT_INS


@pytest.mark.parametrize("format_id, source, suffix", SAMPLES)
def test_untouched_document_round_trips_byte_identically(format_id: str, source: str, suffix: str,
                                                         tmp_path: Path) -> None:
    """An unmodified document renders back its own bytes in memory and through the filesystem."""
    encoded = source.encode("utf-8")
    explicit = facade.loads(source, format_id=format_id)
    assert facade.dumps(explicit) == encoded
    assert (explicit.format_id, explicit.source_format_id) == (format_id, format_id)
    assert explicit.document_version == 1 and explicit.fallback_diagnostic is None
    by_extension = facade.loads(source, file_path=f"sample{suffix}")
    assert facade.dumps(by_extension) == encoded and by_extension.format_id == format_id
    original = tmp_path / f"sample{suffix}"
    original.write_bytes(encoded)
    document = facade.load(original)
    assert document.path == original and facade.dumps(document) == encoded
    target = tmp_path / f"copy{suffix}"
    assert facade.save(document, target) == target and document.path == target
    assert target.read_bytes() == encoded and facade.dumps(facade.load(target)) == encoded


def test_unparsable_source_degrades_to_plain_text(tmp_path: Path) -> None:
    """{p058}: the one authorized fallback still renders the ORIGINAL bytes; declined, it raises."""
    broken = tmp_path / "broken.py"
    broken.write_bytes(BROKEN_PYTHON.encode("utf-8"))
    document = facade.load(broken)
    assert document.source_format_id == "python" and document.fallback_diagnostic is not None
    assert document.format_id == facade.PLAIN_TEXT_FORMAT_ID == "plain_text"
    assert facade.dumps(document) == BROKEN_PYTHON.encode("utf-8")
    with pytest.raises(TreeEngineException) as failure:
        facade.load(broken, allow_plain_text_fallback=False)
    assert failure.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert failure.value.plain_text_fallback_permitted is True


def test_every_caller_reachable_error_is_typed_and_carries_a_real_code(tmp_path: Path) -> None:
    """{p023}: one reachable failure per stable code, each typed, carrying it, attributing a layer."""
    doc = facade.loads(PYTHON, format_id="python")
    root, child = doc.root.short_id, doc.root.children[0].short_id
    invented, collide = facade.loads(PYTHON, format_id="python"), facade.loads(JSON, format_id="json")
    facade.set_attribute(invented, _first(invented, "python:Name").short_id, "invented", "v")
    taken, sibling = collide.root.children[0].node_id, collide.root.children[1].short_id
    cases = (("unknown format_id", lambda: facade.loads("x", format_id="nope"),
              ErrorCode.FORMAT_PLUGIN_NOT_FOUND, ErrorLayer.PLUGIN),
             ("unknown extension", lambda: facade.loads("x", file_path="a.unknown"),
              ErrorCode.FORMAT_UNKNOWN_EXTENSION, ErrorLayer.PLUGIN),
             ("missing file", lambda: facade.load(tmp_path / "absent.py"),
              ErrorCode.STORAGE_IO_ERROR, ErrorLayer.STORAGE),
             ("save without a path", lambda: facade.save(facade.loads(JSON, format_id="json")),
              ErrorCode.STORAGE_IO_ERROR, ErrorLayer.STORAGE),
             ("malformed selector", lambda: facade.query(doc, "[[["),
              ErrorCode.INVALID_SELECTOR, ErrorLayer.CORE),
             ("unknown address", lambda: facade.resolve_address(doc, 10 ** 6),
              ErrorCode.NODE_NOT_FOUND, ErrorLayer.CORE),
             ("stale version", lambda: facade.delete(doc, child, expected_version=99),
              ErrorCode.DOCUMENT_VERSION_CONFLICT, ErrorLayer.CORE),
             ("unknown position",
              lambda: facade.insert(doc, "x = 1\n", position="nowhere", parent=root),
              ErrorCode.INVALID_POSITION, ErrorLayer.CORE),
             ("structureless fragment",
              lambda: facade.insert(doc, "   ", position="last_child", parent=root),
              ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED, ErrorLayer.PLUGIN),
             ("non-primitive attribute", lambda: facade.set_attribute(doc, child, "x", [1]),
              ErrorCode.INVALID_PARENT_TYPE, ErrorLayer.CORE),
             ("node_id collision", lambda: facade.replace_node_id(collide, sibling, taken),
              ErrorCode.NODE_ID_CONFLICT, ErrorLayer.CORE),
             ("plugin refuses the node", lambda: facade.dumps(invented),
              ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR, ErrorLayer.PLUGIN))
    for label, call, code, layer in cases:
        with pytest.raises(TreeEngineException) as failure:
            call()
        assert (label, failure.value.code, failure.value.layer) == (label, code, layer)
        assert str(failure.value).startswith(f"[{code.value}]")


def test_every_address_form_resolves_and_bad_addresses_are_rejected() -> None:
    """{j9rh}: every address form resolves alike; unknown and foreign ones raise before any work."""
    document = facade.loads(PYTHON, format_id="python")
    node = document.root.children[0]
    for address in (node.node_id, str(node.node_id), node.short_id, hex(node.short_id),
                    f"{document.document_id}:{node.node_id}"):
        assert facade.resolve_address(document, address) == node.node_id
    other = facade.loads(JSON, format_id="json")
    foreign = other.root.children[0].node_id
    for bad in (10 ** 6, uuid4(), foreign, f"{other.document_id}:{foreign}"):
        with pytest.raises(TreeEngineException) as failure:
            facade.resolve_address(document, bad)
        assert failure.value.code is ErrorCode.NODE_NOT_FOUND
    with pytest.raises(TreeEngineException):
        facade.delete(document, foreign)
    assert facade.dumps(document) == PYTHON.encode() and document.document_version == 1


def test_expected_version_rejects_a_stale_operation_without_touching_the_document() -> None:
    """{p024}: a stale ``expected_version`` changes nothing, the current one advances it."""
    document = facade.loads(PYTHON, format_id="python")
    before = facade.dumps(document)
    with pytest.raises(TreeEngineException) as failure:
        facade.delete(document, document.root.children[0].short_id, expected_version=99)
    assert failure.value.code is ErrorCode.DOCUMENT_VERSION_CONFLICT
    assert failure.value.details == {"expected_version": 99, "current_version": 1}
    assert facade.dumps(document) == before and document.document_version == 1
    facade.insert(document, "x = 1\n", position="last_child", parent=document.root.short_id, expected_version=1)
    assert document.document_version == 2 and facade.dumps(document) != before
    facade.insert(document, "y = 2\n", position="last_child", parent=document.root.short_id)
    assert document.document_version == 3


def test_insert_delete_and_replace_change_the_rendered_output() -> None:
    """The three sequence mutations reach the render: each produces the exact new source."""
    inserted = facade.loads(PYTHON, format_id="python")
    added = facade.insert(inserted, "def c():\n    return 3\n", position="last_child", parent=inserted.root.short_id)
    assert isinstance(added, facade.MutationResult) and len(added.inserted) == 1
    assert facade.dumps(inserted) == PYTHON.encode() + b"def c():\n    return 3\n"
    deleted = facade.loads(PYTHON, format_id="python")
    removed = facade.delete(deleted, deleted.root.children[0].short_id)
    assert len(removed.removed) == 1 and facade.dumps(deleted) == b"\n\ndef b():\n    return 2\n"
    replaced = facade.loads(PYTHON, format_id="python")
    swap = facade.replace(replaced, replaced.root.children[0].short_id, "def z():\n    return 9\n")
    assert len(swap.removed) == 1 and len(swap.inserted) == 1
    assert facade.dumps(replaced) == b"def z():\n    return 9\n\n\ndef b():\n    return 2\n"


def test_move_reorders_within_a_document_and_transfers_between_two() -> None:
    """{p035}: a move reorders the render; across two documents both stay renderable."""
    document = facade.loads(JSON, format_id="json")
    reorder = facade.move(document, document.root.children[1].short_id, position="first_child",
                          parent=document.root.short_id)
    assert isinstance(reorder, facade.MoveResult)
    assert facade.dumps(document) == b'{"b": 2, "a": 1}'
    source, target = facade.loads(JSON, format_id="json"), facade.loads('{"c": 3}', format_id="json")
    moved = source.root.children[0]
    facade.move(source, moved.short_id, position="last_child", parent=target.root.short_id,
                target_document=target)
    assert facade.dumps(source) == b'{"b": 2}' and facade.dumps(target) == b'{"c": 3, "a": 1}'
    assert moved.node_id not in source.nodes_by_id and moved.node_id in target.nodes_by_id


def test_copy_apply_set_body_replace_node_id_and_reparse_keep_the_document_renderable() -> None:
    """The remaining entry points, each on its documented result type and its effect."""
    document = facade.loads(JSON, format_id="json")
    address, origin = document.root.children[0].short_id, document.root.children[0].node_id
    fresh, kept = facade.copy_subtree(document, address), facade.copy_subtree(document, address, preserve_ids=True)
    assert isinstance(fresh, facade.CopiedDocument) and fresh.origin_document_id is None
    assert fresh.root.node_id != origin and kept.root.node_id == origin  # {p073} minting vs {p074}
    assert kept.origin_document_id == document.document_id
    assert isinstance(facade.apply_subtree(document, fresh), facade.ApplySubtreeResult)
    node = document.root.children[0]
    old_id, short_id, new_id = node.node_id, node.short_id, uuid4()
    assert isinstance(facade.replace_node_id(document, short_id, new_id), facade.AddressRemap)
    assert new_id in document.nodes_by_id and old_id not in document.nodes_by_id
    assert document.nodes_by_id[new_id].short_id == short_id
    body = facade.loads("def a():\n    return 1\n", format_id="python")
    facade.set_body(body, _first(body, "python:IndentedBlock").short_id, "return 42\n")
    assert facade.dumps(body) == b"def a():\n    return 42\n"
    assert facade.reparse(body) is body and body.document_version == 3
    assert body.fallback_diagnostic is None and facade.dumps(body) == b"def a():\n    return 42\n"


def test_query_and_drill_down_return_the_documented_read_only_shapes() -> None:
    """``query`` yields ``QueryMatch``, ``drill_down`` an ``OutlineResponse``; neither mutates."""
    document = facade.loads(PYTHON, format_id="python")
    matches = facade.query(document, "FunctionDef:*")
    assert len(matches) == 2 and all(isinstance(match, facade.QueryMatch) for match in matches)
    assert all(match.node_id and match.short_id_hex.startswith("0x") for match in matches)
    outline = facade.drill_down(document, document.root.short_id, depth=1, include_source=facade.SOURCE_NONE)
    assert isinstance(outline, facade.OutlineResponse) and outline.nodes
    assert outline.meta.document_version == document.document_version == 1
    assert outline.truncation.truncated is False and facade.dumps(document) == PYTHON.encode()


def test_third_party_plugin_registers_resolves_by_extension_and_round_trips(
        registered_kvd_plugin: _KeyValuePlugin, tmp_path: Path) -> None:
    """``register_format_plugin`` joins the registry AND the extension table, and edits render."""
    assert facade.list_formats() == BUILT_INS + (KVD_FORMAT_ID,)
    path = tmp_path / "data.kvd"
    path.write_bytes(KVD_SOURCE.encode("utf-8"))
    document = facade.load(path)
    assert document.format_id == document.source_format_id == KVD_FORMAT_ID
    assert facade.dumps(document) == KVD_SOURCE.encode("utf-8")
    assert [node.fields["key"] for node in document.root.children] == ["alpha", "beta"]
    facade.insert(document, "gamma=3\n", position="last_child", parent=document.root.short_id)
    assert facade.dumps(document) == b"alpha=1\nbeta=2\ngamma=3\n"
    facade.save(document, tmp_path / "out.kvd")
    assert facade.dumps(facade.load(tmp_path / "out.kvd")) == b"alpha=1\nbeta=2\ngamma=3\n"
    (tmp_path / "bad.kvd").write_bytes(b"no separator here\n")  # {p023}: no unauthorized fallback
    with pytest.raises(TreeEngineException) as failure:
        facade.load(tmp_path / "bad.kvd")
    assert failure.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED


def test_documented_limits_fail_typed_rather_than_silently_not_rendering() -> None:
    """An invented attribute only the plugin can refuse fails at render time; an ambiguous parent
    refuses the splice up front."""
    document = facade.loads(PYTHON, format_id="python")
    facade.set_attribute(document, _first(document, "python:Name").short_id, "invented", "v")
    with pytest.raises(TreeEngineException) as render_failure:
        facade.dumps(document)
    assert render_failure.value.code is ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert render_failure.value.layer is ErrorLayer.PLUGIN
    ambiguous = facade.loads("class C:\n    def m(self):\n        return 1\n", format_id="python")
    with pytest.raises(TreeEngineException) as parent_failure:
        facade.insert(ambiguous, "def n(self):\n    return 2\n", position="last_child",
                      parent=_first(ambiguous, "python:ClassDef").short_id)
    assert parent_failure.value.code is ErrorCode.INVALID_PARENT_TYPE
    assert parent_failure.value.layer is ErrorLayer.CORE
    facade.insert(ambiguous, "def n(self):\n    return 2\n", position="last_child",
                  parent=_first(ambiguous, "python:IndentedBlock").short_id)
    assert b"def n(self):" in facade.dumps(ambiguous)


def test_set_attribute_is_rendered_on_an_untouched_cached_source_document() -> None:
    """An accepted, version-bumping attribute edit must reach the rendered output.

    Regression: `set_attribute` was once the only mutating entry point that did
    not invalidate the cached source slice its ancestors hold, so on a
    cache-replaying format (JSON `raw`, BSL `content`, TOML `raw`) the edit was
    accepted and the version bumped while `dumps()` replayed the pre-edit text --
    silently wrong bytes, no error. It now invalidates like every sibling."""
    document = facade.loads(JSON, format_id="json")
    facade.set_attribute(document, _first(document, "json:Member").short_id, "key", "renamed")
    assert document.document_version == 2 and b"renamed" in facade.dumps(document)


def test_set_attribute_is_rendered_where_no_cached_source_masks_it() -> None:
    """The xfail's counterpart: a fields-composing format renders the edit, as does a cleared cache."""
    python = facade.loads(PYTHON, format_id="python")
    facade.set_attribute(python, _first(python, "python:Name").short_id, "value", "renamed")
    assert facade.dumps(python) == b"def renamed():\n    return 1\n\n\ndef b():\n    return 2\n"
    document = facade.loads(JSON, format_id="json")
    facade.move(document, document.root.children[1].short_id, position="first_child",
                parent=document.root.short_id)
    facade.set_attribute(document, document.root.children[0].short_id, "key", "renamed")
    assert facade.dumps(document) == b'{"renamed": 2, "a": 1}'


def test_facade_only_arc_runs_in_a_pristine_interpreter(tmp_path: Path) -> None:
    """IMPORT DISCIPLINE, mechanically: a subprocess script whose only engine import is the facade
    runs a real arc, then asserts the facade is still the ONLY engine module bound there."""
    script = tmp_path / "facade_only_arc.py"
    script.write_text(FACADE_ONLY_ARC, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True, timeout=120,
        env={"PYTHONPATH": ":".join(path for path in sys.path if path), "PATH": "/usr/bin"})
    assert completed.returncode == 0, completed.stderr
    assert "FACADE_ONLY_ARC_OK" in completed.stdout
