"""AI Editor MCP command surface -> ``tree_engine`` adapter (G-029/T-001/A-003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Concept C-023. A pure translation layer -- command registry, parameter mapper,
error translator, result normalizer, comparison-mode trace hook -- with no engine
logic: every substantive operation is delegated to an already-merged engine module
(``plugins.selection``/``registry``/``fallback``, ``query.engine``/``inspection``,
``storage.file_txn``).

Honesty rules bounding what this surface claims: only operations that really run
against the real engine are exposed, and every baseline (CAS commit ``8fb05d1f``)
command defined over a Code Analysis edit session or a mutation pipeline the new
package does not publish yet is listed, with its reason, in
:data:`UNAVAILABLE_BASELINE_COMMANDS` instead of being stubbed; every exposed command
drops the baseline ``project_id``/``session_id`` pair for a real ``file_path``, with
that and every other divergence recorded in :data:`COMMAND_SPECS`; and every success
envelope carries the ``compat_matrix`` verdict for the capabilities that command
needs on the resolved format, so a caller sees non-SUPPORTED coverage, not a claim.
"""

from __future__ import annotations

import enum
import hashlib
import importlib
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, cast

from adapter.compat_matrix import COMPATIBILITY_MATRIX, by_format, validate_adapter_coverage
from tree_engine.core.nodes import Document, walk
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import exception_for_code
from tree_engine.plugins.fallback import build_fallback_tree
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.plugins.selection import build_extension_table, resolve_format_plugin
from tree_engine.query.engine import TreeQueryEngine
from tree_engine.query.inspection import drill_down
from tree_engine.query.selector import QueryParseError
from tree_engine.storage.file_txn import (FileWrite, StorageIOError as
                                          FileTransactionIOError, publish)

__all__ = ["AdapterContractError", "CommandSpec", "CommandTrace", "TraceHook",
           "COMMAND_SPECS", "UNAVAILABLE_BASELINE_COMMANDS", "NOT_RECORDED",
           "MCPAdapter", "raise_for_result"]

#: Used when ``compat_matrix`` has no row for a (format_id, capability) pair.
NOT_RECORDED = "not_recorded_in_matrix"

#: Every format-plugin singleton merged here, loaded live; absent = skipped.
_PLUGIN_SPECS: Tuple[Tuple[str, str], ...] = (
    ("tree_engine.plugins.python.plugin", "PYTHON_FORMAT_PLUGIN"),
    ("tree_engine.plugins.bsl.plugin", "BSL_FORMAT_PLUGIN"),
    ("tree_engine.plugins.plain_text", "PLAIN_TEXT_FORMAT_PLUGIN"),
    ("tree_engine.plugins.json_format", "JSON_FORMAT_PLUGIN"),
    ("tree_engine.plugins.toml_format", "TOML_FORMAT_PLUGIN"),
    ("tree_engine.plugins.yaml.plugin", "YAML_FORMAT_PLUGIN"),
)

#: Exception types with no ``code``/``error_code`` whose identity fixes a code.
_TYPE_CODES: Tuple[Tuple[type, ErrorCode], ...] = (
    (FileTransactionIOError, ErrorCode.STORAGE_IO_ERROR),
    (QueryParseError, ErrorCode.INVALID_SELECTOR),
    (OSError, ErrorCode.STORAGE_IO_ERROR),
)


class AdapterContractError(Exception):
    """Unknown command, or parameters a signature cannot bind. Carries no ``ErrorCode``
    on purpose: the frozen catalog has none for validation, and one invented here
    would misreport an adapter-boundary problem as an engine outcome."""

    def __init__(self, message: str, **details: Any) -> None:
        self.details: Mapping[str, Any] = dict(details)
        super().__init__(message)


@dataclass(frozen=True)
class CommandSpec:
    """Registry row: baseline command, matrix capabilities, approved divergences."""

    name: str
    method: str
    baseline_command: str
    required_capabilities: Tuple[str, ...]
    divergences: Tuple[str, ...]


@dataclass(frozen=True)
class CommandTrace:
    """Comparison-mode record: params BEFORE the call, result/exception AFTER it."""
    command: str
    params: Mapping[str, Any]
    result: Optional[Mapping[str, Any]] = None
    exception: Optional[str] = None
    old_result: Optional[Mapping[str, Any]] = None

    def divergence(self) -> Optional[Dict[str, Any]]:
        """``None`` when the sides agree or no ``old_result`` was set."""
        if self.old_result is None or self.old_result == self.result:
            return None
        old, new = dict(self.old_result), dict(self.result or {})
        keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        return {"command": self.command, "keys": keys, "old": old, "new": new}


TraceHook = Callable[[CommandTrace], None]


def _error_code_of(exc: BaseException) -> Optional[ErrorCode]:
    """Catalog code of ``exc``: ``code`` (typed ``tree_engine.exceptions``) wins;
    ``error_code`` (older ``plugins.contract``/``selection``/``registry``) is read
    only to translate it, never propagated on, and ``details["error_code"]`` covers
    ``QueryParseError``; ``None`` = not classifiable, so the caller re-raises."""
    for attribute in ("code", "error_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, ErrorCode):
            return value
    details = getattr(exc, "details", None)
    if isinstance(details, Mapping) and isinstance(details.get("error_code"), ErrorCode):
        return details["error_code"]
    for exception_type, code in _TYPE_CODES:
        if isinstance(exc, exception_type):
            return code
    return None


def _unwrap(exc: BaseException) -> BaseException:
    """Original exception behind a wrapper: ``lark`` raises ``VisitError`` around the
    selector transformer, hiding a real ``QueryParseError``/INVALID_SELECTOR in
    ``orig_exc``; that wrapper must never reach a caller untyped."""
    original = getattr(exc, "orig_exc", None)
    return original if isinstance(original, BaseException) else exc


def _jsonable(value: Any) -> Any:
    """Engine result -> JSON-safe primitives: dataclasses field-by-field, enums by
    value, bytes decoded round-trip-safely, rest ``str``."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, enum.Enum):
        return _jsonable(value.value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="surrogateescape")
    return str(value)


def raise_for_result(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Structured error envelope -> this project's typed exception for its code."""
    if result.get("success"):
        return result
    error = dict(result.get("error") or {})
    raise exception_for_code(ErrorCode(str(error.get("code"))))(
        str(error.get("message", "")), **dict(error.get("details") or {}))


class MCPAdapter:
    """Registry-driven translation of baseline MCP commands onto the engine. Every
    command returns a normalized envelope, never an engine object and never a bare
    exception. Success: ``{"success": True, "command", "format_id", "capabilities":
    {capability: matrix_status}, "data": {...}}``; failure: ``{"success": False,
    "command", "error": {"code": <ErrorCode value>, "message", "details"}}``. An
    unclassifiable exception is re-raised, never given a fake code."""

    def __init__(self, *, trace_hook: Optional[TraceHook] = None) -> None:
        self._registry = FormatPluginRegistry()
        self._plugins: Dict[str, Any] = {}
        for module_path, attribute in _PLUGIN_SPECS:
            try:
                module = importlib.import_module(module_path)
            except ModuleNotFoundError:
                continue
            plugin = getattr(module, attribute)
            self._registry.register_format_plugin(plugin)
            self._plugins[plugin.metadata.format_id] = plugin
        self._extension_table = build_extension_table(self._plugins)
        self._trace_hook = trace_hook

    @property
    def format_ids(self) -> Tuple[str, ...]:
        """Format ids really registered here; command names are ``COMMAND_SPECS``."""
        return tuple(sorted(self._plugins))

    def command_for(self, command: str) -> Callable[..., Dict[str, Any]]:
        """Bound callable for ``command``: dispatch wiring, fixtures, hooks."""
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            raise AdapterContractError(f"unknown command {command!r}", command=command)
        return cast(Callable[..., Dict[str, Any]], getattr(self, spec.method))

    def dispatch(self, command: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Run ``command``; unbindable params raise :class:`AdapterContractError`."""
        handler = self.command_for(command)
        try:
            return handler(**dict(params))
        except TypeError as exc:
            raise AdapterContractError(f"{command}: {exc}", command=command) from exc

    def implemented_capabilities(self) -> Dict[str, Tuple[str, ...]]:
        """Capabilities really exercised per format id, for the matrix validator."""
        used = sorted({c for s in COMMAND_SPECS.values() for c in s.required_capabilities})
        return {format_id: tuple(used) for format_id in self.format_ids}

    def coverage_gaps(self) -> Tuple[Any, ...]:
        """SUPPORTED/PARTIAL matrix rows this surface does not cover."""
        return validate_adapter_coverage(self.implemented_capabilities(), COMPATIBILITY_MATRIX)

    def universal_file_open(self, file_path: str, format_id: Optional[str] = None,
                            allow_fallback: bool = False) -> Dict[str, Any]:
        """Baseline ``universal_file_open`` minus the CA session."""
        return self._invoke("universal_file_open", self._open, file_path=file_path,
                            format_id=format_id, allow_fallback=allow_fallback)

    def universal_file_preview(self, file_path: str, format_id: Optional[str] = None,
                               select: Optional[str] = None, address: Optional[Any] = None,
                               depth: int = 1, expand_below_bytes: int = 8192,
                               include_source: str = "preview", source_preview_bytes: int = 256,
                               max_output_bytes: int = 65536,
                               allow_fallback: bool = False) -> Dict[str, Any]:
        """Baseline ``universal_file_preview``: ``drill_down``'s ``model_outline``,
        rooted at the root, the first ``select`` match, or a raw ``address``; addresses
        are minted per parse, so ``select`` is the durable way to point at a node."""
        return self._invoke(
            "universal_file_preview", self._preview, file_path=file_path, format_id=format_id,
            select=select, address=address, depth=depth, expand_below_bytes=expand_below_bytes,
            include_source=include_source, source_preview_bytes=source_preview_bytes,
            max_output_bytes=max_output_bytes, allow_fallback=allow_fallback)

    def universal_file_search(self, file_path: str, query: str, format_id: Optional[str] = None,
                              include_code: bool = False, max_results: Optional[int] = None,
                              ) -> Dict[str, Any]:
        """Baseline ``universal_file_search``, xpath mode, via ``TreeQueryEngine``."""
        return self._invoke("universal_file_search", self._search, file_path=file_path,
                            query=query, format_id=format_id, include_code=include_code,
                            max_results=max_results)

    def universal_file_write(self, file_path: str, target_path: Optional[str] = None,
                             content: Optional[str] = None,
                             format_id: Optional[str] = None) -> Dict[str, Any]:
        """Baseline ``universal_file_write``: one recoverable file_txn publish."""
        return self._invoke("universal_file_write", self._write, file_path=file_path,
                            target_path=target_path, content=content, format_id=format_id)

    def universal_file_capabilities(self, format_id: Optional[str] = None) -> Dict[str, Any]:
        """Adapter-native command: per-format, per-command matrix verdict."""
        return self._invoke("universal_file_capabilities", self._capabilities, format_id=format_id)

    def _open(self, file_path: str, format_id: Optional[str], allow_fallback: bool) -> Any:
        resolved, document, fallback = self._document_for(file_path, format_id, allow_fallback)
        return resolved, self._header(document, fallback)

    def _preview(self, file_path: str, format_id: Optional[str], select: Optional[str],
                 address: Optional[Any], allow_fallback: bool, **opts: Any) -> Any:
        resolved, document, fallback = self._document_for(file_path, format_id, allow_fallback)
        if select is not None:
            found = TreeQueryEngine(document, self._plugins[resolved]).query(select)
            address = found[0].node_id if found else f"selector matched no node: {select!r}"
        outline = _jsonable(drill_down(document, address, **opts))
        return resolved, {"outline": outline, **self._header(document, fallback)}

    def _search(self, file_path: str, query: str, format_id: Optional[str],
                include_code: bool, max_results: Optional[int]) -> Any:
        resolved, document, _fb = self._document_for(file_path, format_id, False)
        engine = TreeQueryEngine(document, self._plugins[resolved])
        matches = engine.query(query, include_source=include_code)
        limited = matches if max_results is None else matches[: max(int(max_results), 0)]
        return resolved, {"query": query, "total": len(matches), "matches": _jsonable(limited)}

    def _write(self, file_path: str, target_path: Optional[str],
               content: Optional[str], format_id: Optional[str]) -> Any:
        payload = content.encode("utf-8") if content is not None else Path(file_path).read_bytes()
        plugin = self._resolve(file_path, format_id)
        generated = plugin.generate_output(plugin.parse_document(payload))
        data = generated.encode("utf-8") if isinstance(generated, str) else generated
        target = Path(target_path) if target_path else Path(file_path)
        publish([FileWrite(target_path=target, content=data)], target.parent / f"{target.name}.jrnl")
        return plugin.metadata.format_id, {
            "target_path": str(target), "bytes_written": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "byte_identical": data == payload}

    def _capabilities(self, format_id: Optional[str]) -> Any:
        if format_id is not None:
            self._registry.get_format_plugin(format_id)  # raises FORMAT_PLUGIN_NOT_FOUND
        return format_id or "*", {
            "formats": {fid: {s.name: self._coverage(fid, s.required_capabilities)
                              for s in COMMAND_SPECS.values()}
                        for fid in ((format_id,) if format_id else self.format_ids)},
            "unavailable_baseline_commands": dict(UNAVAILABLE_BASELINE_COMMANDS),
            "matrix_gaps": _jsonable(self.coverage_gaps())}

    def _resolve(self, file_path: str, format_id: Optional[str]) -> Any:
        """Format selection delegated whole to ``plugins.selection``."""
        return resolve_format_plugin(format_id=format_id, file_path=file_path, registry=self._registry,
                                     extension_table=self._extension_table)

    def _document_for(self, file_path: str, format_id: Optional[str], allow_fallback: bool
                      ) -> Tuple[str, Document, Optional[Mapping[str, Any]]]:
        """Resolve, read, parse (optionally via the sanctioned plain-text fallback)
        and attach the address index ``core.address`` needs -- the one thing the
        merged engine does not publish yet: ``parse_document`` yields a ``Document``
        with no ``nodes_by_id``/``resolve_short_id``, so ``normalize_node_address``
        rejects every address. Built from the engine's ``walk``; facade work."""
        plugin = self._resolve(file_path, format_id)
        resolved = plugin.metadata.format_id
        payload = Path(file_path).read_bytes()
        fallback: Optional[Mapping[str, Any]] = None
        try:
            document = plugin.parse_document(payload)
        except Exception as exc:
            if not allow_fallback:
                raise
            tree = build_fallback_tree(payload, _unwrap(exc), source_format_id=resolved)
            document, fallback = tree.document, _jsonable(tree.metadata)
            resolved = document.representation_format_id
        nodes = {n.node_id: n for n in walk(document.root) if n.node_id is not None}
        shorts = {n.short_id: n.node_id for n in nodes.values() if n.short_id is not None}
        document.nodes_by_id = nodes
        document.resolve_short_id = lambda sid: ([shorts[sid]] if sid in shorts else [])
        return resolved, document, fallback

    @staticmethod
    def _header(doc: Document, fallback: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        return {"source_format_id": doc.source_format_id, "fallback": fallback,
                "representation_format_id": doc.representation_format_id,
                "node_count": len(doc.nodes_by_id),
                "root": {"node_id": str(doc.root.node_id), "short_id": doc.root.short_id}}

    @staticmethod
    def _coverage(format_id: str, capabilities: Tuple[str, ...]) -> Dict[str, str]:
        recorded = {r.capability: r.coverage.value for r in by_format(format_id, COMPATIBILITY_MATRIX)}
        return {capability: recorded.get(capability, NOT_RECORDED) for capability in capabilities}

    def _invoke(self, command: str, run: Callable[..., Any], **params: Any) -> Dict[str, Any]:
        """Trace, execute, translate; the only place the trace hook fires."""
        trace = CommandTrace(command=command, params=dict(params))
        try:
            format_id, data = run(**params)
        except Exception as exc:
            original = _unwrap(exc)
            code = _error_code_of(original)
            if code is None:
                self._emit(replace(trace, exception=repr(original)))
                raise
            result = {"success": False, "command": command, "error": {
                "code": code.value, "message": str(original),
                "details": _jsonable(getattr(original, "details", {}) or {})}}
        else:
            caps = COMMAND_SPECS[command].required_capabilities
            result = {"success": True, "command": command, "format_id": format_id,
                      "capabilities": self._coverage(format_id, caps), "data": data}
        self._emit(replace(trace, result=result))
        return result

    def _emit(self, trace: CommandTrace) -> None:
        if self._trace_hook is not None:  # comparison-mode hook
            self._trace_hook(trace)


_STATELESS = ("baseline project_id/session_id dropped: no Code Analysis session store "
              "exists in the new package, so the command is stateless over a file_path")

COMMAND_SPECS: Mapping[str, CommandSpec] = {name: CommandSpec(name, name, baseline, caps, diverge)
                                            for name, baseline, caps, diverge in (
    ("universal_file_open", "universal_file_open", ("parse_document",),
     (_STATELESS, "create/initial_content replaced by allow_fallback, the opt-in "
                  "plain-text fallback of plugins.fallback")),
    ("universal_file_preview", "universal_file_preview", ("parse_document", "cst_query_selector"),
     (_STATELESS, "result is the new model_outline shape, not the baseline payload",
      "node_id/short_id are minted per parse, so a raw address never survives two "
      "stateless calls; select= is the durable addressing form")),
    ("universal_file_search", "universal_file_search",
     ("parse_document", "cst_query_selector", "semantic_role_mapping"),
     (_STATELESS, "search_type fixed to xpath; simple/text modes are not ported",
      "runs on the freshly parsed file, not on an in-memory session draft")),
    ("universal_file_write", "universal_file_write",
     ("parse_document", "export_from_common", "generate_output", "byte_identical_round_trip"),
     (_STATELESS, "publishes regenerated bytes through storage.file_txn; no git, no CA lock")),
    ("universal_file_capabilities", "(none)", (),
     ("adapter-native command with no baseline counterpart; reports matrix verdicts",)),
)}

#: Baseline commands deliberately NOT exposed, each with the real reason.
UNAVAILABLE_BASELINE_COMMANDS: Mapping[str, str] = {
    "universal_file_edit/move_nodes":
        "no public mutation entry point; core.operations and core.move are internal",
    "universal_file_close, session_write/undo/redo":
        "no edit-session lifecycle, no session store and no undo stack are merged",
    "universal_file_node_at_line": "no merged line->node resolver; QueryMatch.range is empty",
    "session_git_*": "git integration is AI Editor infrastructure, out of scope",
    "health/info": "server infrastructure; this module is a library, it starts no server",
}
