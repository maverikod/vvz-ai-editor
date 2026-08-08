"""The format plugins that ship with the engine but whose parser is an optional extra.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: the declaration, and the one import attempt that acts on it. Nothing else in the package
may decide what is optional.

**Why any format is detachable at all.** The engine's data formats -- ``plain_text``, ``json``,
``toml``, ``yaml`` -- either need nothing outside the standard library or need one small, stable
library. The LANGUAGE formats do not: ``python`` wraps LibCST and ``bsl`` wraps tree-sitter plus a
separately-released 1C grammar. Those track external toolchains on their own schedule, and that
schedule has already forced this project's hand once -- ``tree-sitter>=0.25,<0.26`` exists because
``tree-sitter-bsl`` 0.1.6 reports grammar ABI 15, which the 0.24 line cannot load. Keeping the two
language plugins detachable means that churn cannot stop a consumer who only ever opens a JSON
file from importing the engine at all. Before this module, ``facade.py`` imported both eagerly, so
``import tree_engine.facade`` failed without LibCST AND without tree-sitter: the extras that
declare them optional were a fiction.

**What detachable does NOT mean.** It does not mean degrading. When a detached plugin's format is
actually requested and its library is absent, the engine refuses with a declared, typed error that
names the extra to install ({p023}) -- never an ``ImportError`` traceback escaping the facade, and
never a quiet reinterpretation of a 1C module or a Python file as plain text. A wrong answer that
looks like an answer is worse than a refusal.

This module imports nothing heavy itself: it holds strings and calls :func:`importlib.import_module`
only when asked. The plugin modules read their own extensions back out of it, so the table the
facade builds for a DETACHED plugin and the metadata that plugin declares when it is present can
never drift apart.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from typing import Any, Optional, Tuple

__all__ = ["BSL_PLUGIN_SPEC", "DETACHABLE_PLUGIN_SPECS", "PYTHON_PLUGIN_SPEC",
           "DetachablePluginSpec", "load_detachable_plugin"]


@dataclass(frozen=True)
class DetachablePluginSpec:
    """One shipped format whose parser library is an optional install.

    ``module``/``attribute`` locate the ready-made plugin singleton without importing it;
    ``requirements`` are the import names that may be missing -- every library the format needs at
    RUN time, not only the ones its module imports at load time -- and ``extra`` is the name a
    consumer installs to get them, so the refusal can say exactly what to do. ``file_extensions`` is the same
    tuple the plugin's own metadata declares -- the plugin reads it from here -- so the facade can
    still map a path to this format, and refuse by name, while the plugin itself is unimportable.
    """

    format_id: str
    module: str
    attribute: str
    requirements: Tuple[str, ...]
    extra: str
    file_extensions: Tuple[str, ...]

    def unavailable_message(self, missing: str, detail: str) -> str:
        """The refusal a caller sees when this format is requested and its library is absent."""
        return (f"format {self.format_id!r} is available only with the {self.extra!r} extra: "
                f"{missing} could not be imported ({detail}). Install it with "
                f"pip install 'ai-editor-tree-engine[{self.extra.removeprefix('tree-engine-')}]' "
                f"-- the engine does not reinterpret a {self.format_id} file as another format.")


#: LibCST. Python's tree, identity and byte-identical round trip all come from it, and
#: ``plugins/python/plugin.py`` imports it at module level, so its absence is visible immediately.
PYTHON_PLUGIN_SPEC = DetachablePluginSpec(
    format_id="python", module="tree_engine.plugins.python.plugin",
    attribute="PYTHON_FORMAT_PLUGIN", requirements=("libcst",), extra="tree-engine-python",
    file_extensions=("py", "pyi"))

#: tree-sitter plus the separately released 1C grammar; see this module's docstring for the ABI
#: constraint that makes detachability load-bearing rather than tidy. Both are named explicitly
#: because ``plugins/bsl`` defers its ``tree_sitter`` import until the first parse, so the plugin
#: module imports perfectly well on a machine that cannot parse a single line of BSL: without this
#: declaration the format would register, then fail at parse time with a classified content error,
#: and the authorized plain-text fallback would hand back a 1C module reinterpreted as text.
BSL_PLUGIN_SPEC = DetachablePluginSpec(
    format_id="bsl", module="tree_engine.plugins.bsl.plugin",
    attribute="BSL_FORMAT_PLUGIN", requirements=("tree_sitter", "tree_sitter_bsl"),
    extra="tree-engine-bsl", file_extensions=("bsl",))

#: In the order the facade registers them, which is the order ``list_formats()`` reports.
DETACHABLE_PLUGIN_SPECS: Tuple[DetachablePluginSpec, ...] = (PYTHON_PLUGIN_SPEC, BSL_PLUGIN_SPEC)


def load_detachable_plugin(spec: DetachablePluginSpec) -> Tuple[Optional[Any], Optional[str]]:
    """Import ``spec``'s plugin singleton, or say why it is unavailable.

    Returns ``(plugin, None)`` when everything the format needs is present, and ``(None, message)``
    when it is not. Each declared requirement is looked for FIRST, with ``find_spec``, which
    locates a module without executing it: a plugin that defers its own parser import until the
    first parse would otherwise import cleanly and be registered as available, and its absence
    would then surface as a parse failure -- which is the one classification allowed to open the
    plain-text fallback. Only an :class:`ImportError` is treated as "not installed"; every other
    failure is a real defect in a plugin that IS installed and propagates unchanged, because
    swallowing it would turn a broken plugin into a missing one and send the consumer to install
    something they already have.
    """
    for requirement in spec.requirements:
        try:
            found = importlib.util.find_spec(requirement)
        except ImportError as exc:
            return None, spec.unavailable_message(requirement, str(exc))
        if found is None:
            return None, spec.unavailable_message(requirement, f"No module named {requirement!r}")
    try:
        module = importlib.import_module(spec.module)
    except ImportError as exc:
        return None, spec.unavailable_message(spec.module, str(exc))
    return getattr(module, spec.attribute), None
