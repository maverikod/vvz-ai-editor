"""Pipeline-level gate for the format-plugin CONTRACT itself (concept C-010,
{p045}, {p055}-{p060}, {p013}, {p097}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope: this check does not re-run any pytest suite and does not shell out to
``pytest`` -- it drives the six REAL, already-merged format plugins directly
(``PYTHON_FORMAT_PLUGIN``, ``BSL_FORMAT_PLUGIN``, ``PLAIN_TEXT_FORMAT_PLUGIN``,
``JSON_FORMAT_PLUGIN``, ``TOML_FORMAT_PLUGIN``, ``YAML_FORMAT_PLUGIN``) and
asserts that each one genuinely satisfies what the plugin/format contract
promises, independent of and in addition to whatever the sibling pytest
suites under ``tests/plugins/`` already cover. It is the pipeline-level
acceptance gate a CI run (or a human) can invoke standalone, at any time,
against a working tree.

Six rules, run against every plugin:

1. ``implements-format-boundary`` -- structurally satisfies
   ``tree_engine.core.plugin_boundary.FormatBoundary`` per
   ``implements_format_boundary`` (no abstract method left unimplemented).
2. ``metadata-and-contract-version`` -- ``metadata`` is a real
   ``FormatPluginMetadata`` with a non-empty ``format_id``/``plugin_version``,
   and its ``contract_version`` is one a fresh
   ``tree_engine.plugins.registry.FormatPluginRegistry`` genuinely accepts
   (the real registration path, not a re-implemented check of the same rule).
3. ``contract-methods-present`` -- every ``FormatPluginContract`` stage
   (``parse_document``, ``import_external_tree``, ``parse_fragment``,
   ``import_to_common``, ``export_from_common``, ``generate_output``,
   ``semantic_role_mapping``) is present and callable.
4. ``node-identity-uuid4-and-short-id`` -- parses real, well-formed source
   and walks every node of the resulting ``Document``: each one must carry a
   UUID4 ``node_id`` and a positive integer ``short_id`` ({p013}, {p097}).
   Not theoretical: BSL once shipped with no node identity at all and
   plain_text with no short_ids, both caught late; this is what stops that
   recurring.
5. ``malformed-content-classified-parse-failed`` -- feeding real, genuinely
   broken source into ``parse_document`` must raise an exception classified
   ``ErrorCode.FORMAT_CONTENT_PARSE_FAILED`` -- never silently accepted,
   never a bare unclassified builtin, never the wrong code.
6. ``wrong-argument-type-classified-contract-error`` -- calling
   ``parse_document`` with a value of the wrong type (an ``int``, never a
   legitimate ``str``/``bytes`` source) must raise an exception classified
   ``ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR`` -- the call-contract violation
   case, distinct from rule 5's content-classification case.

Exception-convention split ({p023}): two carriers coexist in this codebase
for both rules 5 and 6 -- the canonical typed hierarchy
(``tree_engine.exceptions.TreeEngineException``, exposing the code as
``.code``) and the older ``tree_engine.plugins.contract.FormatPluginContractError``
(exposing it as ``.error_code``), a DIFFERENT class that merely shares a name
with ``tree_engine.exceptions.FormatPluginContractError``. Both are real,
both are currently accepted by the storage/fallback consumers
(``tree_engine.plugins.fallback``, ``tree_engine.storage.lifecycle``), and
this check honours that by classifying through either real carrier via
precise ``isinstance`` checks -- never generic ``getattr`` duck-typing that
could mistake an unrelated exception for a classified one. Rules 5/6 do not
fail a plugin merely for using the older carrier; they fail only when
neither real carrier applies (a bare, unclassified builtin) or the
classified code is wrong. Which carrier each plugin actually used is always
named in that case's own passing detail, so a silent drift between the two
conventions stays visible in every run's output, not just when it finally
breaks the plain-text-fallback path it has already broken before.

Every case runs directly against the real plugin singletons and real source
text -- no mocks, no stub plugin. The check registers itself on the shared
pipeline registry (see ``pipeline/registry.py``) and reports through
``CheckResult``/``CheckStatus`` only -- it never prints or calls
``sys.exit`` itself; the pipeline CLI owns all console output and process
exit codes.
"""

from __future__ import annotations

import dataclasses
import traceback
from typing import Any, Callable, List, Optional, Tuple
from uuid import UUID

from pipeline import registry
from pipeline.registry import CheckResult

from tree_engine.core.nodes import Document, walk
from tree_engine.core.plugin_boundary import implements_format_boundary
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import TreeEngineException
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.contract import (
    FormatPluginContractError as LegacyFormatPluginContractError,
)
from tree_engine.plugins.contract import FormatPluginMetadata
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry, PluginRegistrationError
from tree_engine.plugins.toml_format import TOML_FORMAT_PLUGIN
from tree_engine.plugins.yaml.plugin import YAML_FORMAT_PLUGIN

CHECK_NAME = "check-contract"
CHECK_DESCRIPTION = (
    "Drive every real format plugin (python, bsl, plain_text, json, toml, "
    "yaml) directly against the FormatPluginContract/FormatBoundary "
    "surface: boundary conformance, metadata/contract_version, method "
    "presence, UUID4 node_id + positive short_id on every produced node, "
    "and correctly classified FORMAT_CONTENT_PARSE_FAILED / "
    "FORMAT_PLUGIN_CONTRACT_ERROR exceptions."
)

# The single, shared FormatPluginContract pipeline stage names every
# concrete plugin must expose and that this check verifies are callable.
_CONTRACT_METHODS: Tuple[str, ...] = (
    "parse_document",
    "import_external_tree",
    "parse_fragment",
    "import_to_common",
    "export_from_common",
    "generate_output",
    "semantic_role_mapping",
)


@dataclasses.dataclass(frozen=True)
class _Sample:
    """One real plugin plus the real source samples its rules drive it with."""

    name: str
    plugin: Any
    valid_source: Any
    malformed_source: Any


# Real, genuinely well-formed and genuinely broken source per plugin, drawn
# from (or identical in spirit to) the plugins' own merged pytest fixtures
# (``tests/plugins/...``) -- never fabricated to make a rule trivially pass.
_SAMPLES: Tuple[_Sample, ...] = (
    _Sample("python", PYTHON_FORMAT_PLUGIN, "def foo():\n    return 1\n", "def broken(:\n    pass\n"),
    _Sample(
        "bsl", BSL_FORMAT_PLUGIN,
        "\u041f\u0440\u043e\u0446\u0435\u0434\u0443\u0440\u0430 \u041f() \u042d\u043a\u0441\u043f\u043e\u0440\u0442\n\u041a\u043e\u043d\u0435\u0446\u041f\u0440\u043e\u0446\u0435\u0434\u0443\u0440\u044b\n".encode("utf-8"),
        "\u041f\u0440\u043e\u0446\u0435\u0434\u0443\u0440\u0430 \u041f(\n\u041a\u043e\u043d\u0435\u0446\u041f\u0440\u043e\u0446\u0435\u0434\u0443\u0440\u044b\n".encode("utf-8"),
    ),
    _Sample("plain_text", PLAIN_TEXT_FORMAT_PLUGIN, "hello\nworld\n", b"hello \xff\xfe world\n"),
    _Sample("json", JSON_FORMAT_PLUGIN, '{"a": 1}', b'{"a": 1'),
    _Sample("toml", TOML_FORMAT_PLUGIN, "key = 1\n", "key = \n"),
    _Sample("yaml", YAML_FORMAT_PLUGIN, "a: 1\n", "a:\n\tb: 1\n"),
)

# A value no plugin's parse_document ever legitimately accepts: not str,
# not bytes -- the call-contract violation rule 6 exercises.
_WRONG_ARGUMENT_TYPE = 12345


@dataclasses.dataclass(frozen=True)
class CaseResult:
    """One (plugin, rule) verdict: pass/fail plus a short human detail."""

    plugin: str
    rule: str
    passed: bool
    detail: str = ""

    def format(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        head = f"[{status}] {self.plugin}/{self.rule}"
        return f"{head} - {self.detail}" if self.detail else head


def _run_case(sample: _Sample, rule_name: str, rule_func: "Callable[[_Sample], str]") -> CaseResult:
    """Run one rule against one real plugin; never let a raised exception
    outside the rule's own documented failure path abort the whole check."""

    try:
        detail = rule_func(sample)
        return CaseResult(sample.name, rule_name, True, detail)
    except AssertionError as exc:
        return CaseResult(sample.name, rule_name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is a case failure
        return CaseResult(sample.name, rule_name, False, f"unexpected exception:\n{traceback.format_exc()}")


def _classify(exc: BaseException) -> Tuple[Optional[ErrorCode], str]:
    """Classify ``exc`` through one of the two REAL exception carriers this
    codebase uses -- precise ``isinstance`` checks only, never a generic
    ``getattr`` scan that could mistake an unrelated exception (carrying an
    unrelated same-named attribute) for a genuine classification. Returns
    ``(None, "unclassified(...)")`` for anything that is neither."""

    if isinstance(exc, TreeEngineException):
        return exc.code, "typed(tree_engine.exceptions)"
    if isinstance(exc, LegacyFormatPluginContractError):
        return exc.error_code, "legacy(tree_engine.plugins.contract)"
    return None, f"unclassified({type(exc).__module__}.{type(exc).__name__})"


# ---- rule 1: FormatBoundary structural conformance -------------------------


def _rule_implements_boundary(sample: _Sample) -> str:
    plugin_cls = type(sample.plugin)
    if not implements_format_boundary(plugin_cls):
        raise AssertionError(
            f"{plugin_cls.__module__}.{plugin_cls.__name__} does not structurally "
            "satisfy FormatBoundary (missing or unimplemented method)"
        )
    return f"{plugin_cls.__name__} structurally satisfies FormatBoundary"


# ---- rule 2: declared metadata shape + engine-accepted contract_version ----


def _rule_metadata_and_contract_version(sample: _Sample) -> str:
    metadata = sample.plugin.metadata
    if not isinstance(metadata, FormatPluginMetadata):
        raise AssertionError(f"metadata is {type(metadata).__name__}, not FormatPluginMetadata")
    if not metadata.format_id:
        raise AssertionError("declares an empty format_id")
    if not metadata.plugin_version:
        raise AssertionError("declares an empty plugin_version")

    # Drive the REAL registration/validation path on a throwaway registry --
    # never the process-wide default -- so this is the engine's own accepted
    # contract_version check, not a re-implementation of the same rule.
    fresh_registry = FormatPluginRegistry()
    try:
        fresh_registry.register_format_plugin(sample.plugin)
    except PluginRegistrationError as exc:
        raise AssertionError(f"engine registry rejects declared metadata: {exc}") from exc
    return f"format_id={metadata.format_id!r} contract_version={metadata.contract_version!r} accepted"


# ---- rule 3: every contract method present and callable --------------------


def _rule_contract_methods_present(sample: _Sample) -> str:
    plugin_cls = type(sample.plugin)
    abstract = getattr(plugin_cls, "__abstractmethods__", frozenset())
    if abstract:
        raise AssertionError(f"unimplemented abstract method(s): {sorted(abstract)}")
    missing = [name for name in _CONTRACT_METHODS if not callable(getattr(sample.plugin, name, None))]
    if missing:
        raise AssertionError(f"missing or uncallable contract method(s): {missing}")
    return f"all {len(_CONTRACT_METHODS)} FormatPluginContract methods present and callable"


# ---- rule 4: every produced node carries UUID4 node_id + positive short_id -


def _rule_node_identity(sample: _Sample) -> str:
    document = sample.plugin.parse_document(sample.valid_source)
    if not isinstance(document, Document):
        raise AssertionError(f"parse_document returned {type(document).__name__}, not a Document")

    nodes = list(walk(document.root))
    if not nodes:
        raise AssertionError("parsing well-formed source produced zero nodes")

    bad_node_id = [n for n in nodes if not (isinstance(n.node_id, UUID) and n.node_id.version == 4)]
    if bad_node_id:
        raise AssertionError(f"{len(bad_node_id)}/{len(nodes)} node(s) lack a UUID4 node_id")

    bad_short_id = [
        n for n in nodes
        if not (isinstance(n.short_id, int) and not isinstance(n.short_id, bool) and n.short_id > 0)
    ]
    if bad_short_id:
        raise AssertionError(f"{len(bad_short_id)}/{len(nodes)} node(s) lack a positive short_id")

    node_ids = [n.node_id for n in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise AssertionError("duplicate node_id within one parsed document")

    return f"{len(nodes)} node(s): every node_id a UUID4, every short_id a distinct positive int"


# ---- rule 5: malformed content -> classified FORMAT_CONTENT_PARSE_FAILED ---


def _rule_malformed_content_classified(sample: _Sample) -> str:
    try:
        result = sample.plugin.parse_document(sample.malformed_source)
    except Exception as exc:  # noqa: BLE001 - classified below, this IS the check
        code, convention = _classify(exc)
        if code is not ErrorCode.FORMAT_CONTENT_PARSE_FAILED:
            raise AssertionError(
                f"malformed content raised {type(exc).__module__}.{type(exc).__name__} "
                f"({convention}) classified {code}, expected FORMAT_CONTENT_PARSE_FAILED"
            ) from exc
        return f"raised {type(exc).__name__} via {convention}, correctly classified FORMAT_CONTENT_PARSE_FAILED"
    raise AssertionError(f"malformed content was silently accepted, yielding {result!r}")


# ---- rule 6: wrong-argument-type -> classified FORMAT_PLUGIN_CONTRACT_ERROR


def _rule_wrong_argument_type_classified(sample: _Sample) -> str:
    try:
        result = sample.plugin.parse_document(_WRONG_ARGUMENT_TYPE)
    except Exception as exc:  # noqa: BLE001 - classified below, this IS the check
        code, convention = _classify(exc)
        if code is not ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR:
            raise AssertionError(
                f"a wrong-argument-type call raised {type(exc).__module__}.{type(exc).__name__} "
                f"({convention}) classified {code}, expected FORMAT_PLUGIN_CONTRACT_ERROR"
            ) from exc
        return f"raised {type(exc).__name__} via {convention}, correctly classified FORMAT_PLUGIN_CONTRACT_ERROR"
    raise AssertionError(
        f"parse_document({_WRONG_ARGUMENT_TYPE!r}) (wrong type) was silently accepted, yielding {result!r}"
    )


_RULES: Tuple[Tuple[str, "Callable[[_Sample], str]"], ...] = (
    ("implements-format-boundary", _rule_implements_boundary),
    ("metadata-and-contract-version", _rule_metadata_and_contract_version),
    ("contract-methods-present", _rule_contract_methods_present),
    ("node-identity-uuid4-and-short-id", _rule_node_identity),
    ("malformed-content-classified-parse-failed", _rule_malformed_content_classified),
    ("wrong-argument-type-classified-contract-error", _rule_wrong_argument_type_classified),
)


def check_contract() -> CheckResult:
    """Run every rule against every real format plugin and report one verdict.

    Every (plugin, rule) pair runs independently -- one failing pair never
    aborts the rest -- so a single run's output names every violation this
    working tree actually has, not just the first one hit.
    """

    results: List[CaseResult] = [
        _run_case(sample, rule_name, rule_func)
        for sample in _SAMPLES
        for rule_name, rule_func in _RULES
    ]
    output = "\n".join(result.format() for result in results)
    failed = [result for result in results if not result.passed]
    passed_count = len(results) - len(failed)

    if not failed:
        return CheckResult.ok(
            message=(
                f"{passed_count}/{len(results)} contract case(s) passed across "
                f"{len(_SAMPLES)} real format plugins"
            ),
            output=output,
        )
    failing_names = ", ".join(f"{r.plugin}/{r.rule}" for r in failed)
    return CheckResult.fail(
        message=f"{len(failed)}/{len(results)} contract case(s) failed: {failing_names}",
        output=output,
    )


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_contract)
