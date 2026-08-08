"""The two language plugins are genuinely detachable, and refuse by name when detached.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: ``tree_engine.plugins.detachable`` and the facade's use of it. The property under test is
one a normal in-process test cannot observe, because this environment HAS LibCST and tree-sitter
installed: that ``import tree_engine.facade`` succeeds on a machine that has neither. So the
central test runs a SUBPROCESS with a real import hook blocking those three module names, imports
the facade there, and asserts both what still works and what is refused. Nothing is stubbed inside
the engine -- the block is applied to the interpreter, exactly as an absent installation would be.

Why it matters. ``facade.py`` used to import both language plugins eagerly, so the
``tree-engine-python`` and ``tree-engine-bsl`` extras were a fiction: a consumer that only ever
opens JSON still could not import the engine without LibCST AND tree-sitter, the second of which
tracks a separately released 1C grammar whose ABI has already forced a version pin once.

The second property is that detaching never degrades. A detached format must be refused with a
typed error naming the extra to install -- not reported as an unknown extension, and above all not
parsed as plain text through the authorized fallback, which would hand back a Python module or a
1C module silently reinterpreted as lines of text.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tree_engine import facade
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import TreeEngineException
from tree_engine.plugins.detachable import (
    BSL_PLUGIN_SPEC, DETACHABLE_PLUGIN_SPECS, PYTHON_PLUGIN_SPEC, DetachablePluginSpec,
    load_detachable_plugin)

DETACHED_ARC = '''
"""Run with every language-parser library blocked, as an install without the extras would be."""
import importlib.abc
import importlib.machinery
import sys

BLOCKED = {"libcst", "tree_sitter", "tree_sitter_bsl"}


class _Blocked(importlib.abc.MetaPathFinder):
    """A real finder that refuses the blocked names, exactly as an absent package would."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


sys.meta_path.insert(0, _Blocked())
for name in list(sys.modules):
    if name.split(".")[0] in BLOCKED:
        del sys.modules[name]

import tree_engine.facade as facade

assert facade.list_formats() == ("json", "toml", "yaml", "plain_text"), facade.list_formats()
assert not (BLOCKED & set(sys.modules)), sorted(BLOCKED & set(sys.modules))

for format_id, suffix, sample in (("json", ".json", '{"a": 1}'),
                                  ("toml", ".toml", "key = 1\\n"),
                                  ("yaml", ".yaml", "a: 1\\n"),
                                  ("plain_text", ".txt", "alpha\\nbravo\\n")):
    for kwargs in ({"format_id": format_id}, {"file_path": "sample" + suffix}):
        document = facade.loads(sample, **kwargs)
        assert facade.dumps(document) == sample.encode(), (format_id, kwargs)

for format_id, suffix, sample, extra in (
        ("python", ".py", "def a():\\n    return 1\\n", "tree-engine-python"),
        ("bsl", ".bsl", "Procedure P()\\nEndProcedure\\n", "tree-engine-bsl")):
    for kwargs in ({"format_id": format_id}, {"file_path": "sample" + suffix}):
        try:
            facade.loads(sample, **kwargs)
        except Exception as error:
            assert type(error).__module__ == "tree_engine.exceptions", type(error)
            assert error.code.value == "FORMAT_PLUGIN_NOT_FOUND", error.code
            assert extra in str(error), str(error)
            assert format_id in str(error), str(error)
        else:
            raise SystemExit(f"{format_id} was accepted with its parser library blocked")

print("DETACHED_ARC_OK")
'''


def test_facade_imports_and_data_formats_work_with_no_language_parser_installed(
        tmp_path: Path) -> None:
    """The whole point, proved by execution: with LibCST, tree-sitter and tree-sitter-bsl all
    unimportable, ``import tree_engine.facade`` succeeds, every data format round-trips
    byte-identically, and each language format is refused with a typed error naming its extra."""
    script = tmp_path / "detached_arc.py"
    script.write_text(DETACHED_ARC, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=120,
        env={"PYTHONPATH": ":".join(path for path in sys.path if path), "PATH": "/usr/bin"})
    assert completed.returncode == 0, completed.stderr
    assert "DETACHED_ARC_OK" in completed.stdout


@pytest.mark.parametrize("spec", DETACHABLE_PLUGIN_SPECS, ids=lambda s: s.format_id)
def test_a_spec_declares_the_extensions_its_own_plugin_declares(spec: DetachablePluginSpec) -> None:
    """The facade maps a path to a DETACHED format through the spec and to an attached one through
    the plugin's metadata; if the two disagreed, ``.py`` would resolve differently depending on
    whether LibCST happened to be installed. The plugin reads the tuple back out of the spec, and
    this asserts that it really is the same one."""
    plugin, refusal = load_detachable_plugin(spec)
    assert plugin is not None and refusal is None, refusal
    assert plugin.metadata.file_extensions == spec.file_extensions
    assert plugin.metadata.format_id == spec.format_id


def test_an_unsatisfied_requirement_is_reported_and_never_raised_as_an_import_error() -> None:
    """A missing library is an answer, not a traceback: the loader reports it as a message naming
    the format and the extra, which is what the facade turns into its typed refusal."""
    absent = DetachablePluginSpec(
        format_id="python", module=PYTHON_PLUGIN_SPEC.module,
        attribute=PYTHON_PLUGIN_SPEC.attribute, requirements=("no_such_parser_library",),
        extra="tree-engine-python", file_extensions=("py",))
    plugin, refusal = load_detachable_plugin(absent)
    assert plugin is None
    assert refusal is not None
    assert "no_such_parser_library" in refusal and "tree-engine-python" in refusal
    assert "pip install 'ai-editor-tree-engine[python]'" in refusal


def test_the_shipped_environment_still_offers_every_format_in_the_documented_order() -> None:
    """With both extras installed -- this environment -- nothing about the public surface moves."""
    assert facade.list_formats() == ("python", "bsl", "json", "toml", "yaml", "plain_text")
    assert facade.dumps(facade.loads("def a():\n    return 1\n", file_path="m.py")) == (
        b"def a():\n    return 1\n")
    assert PYTHON_PLUGIN_SPEC.file_extensions == ("py", "pyi")
    assert BSL_PLUGIN_SPEC.file_extensions == ("bsl",)


def test_an_unknown_extension_is_still_unknown_rather_than_a_detached_format() -> None:
    """The refusal is narrow: only a format the engine really ships answers with "install the
    extra"; anything else is still an unknown extension."""
    with pytest.raises(TreeEngineException) as failure:
        facade.loads("x", file_path="sample.unknown")
    assert failure.value.code is ErrorCode.FORMAT_UNKNOWN_EXTENSION
