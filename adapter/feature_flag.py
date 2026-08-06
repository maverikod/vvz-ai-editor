"""Feature flag governing which engine serves each AI Editor MCP command
(G-029/T-001/A-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Concept C-023, {p034}: after the adapter (A-003) and comparison mode (A-005) are merged,
the migration still needs one more switch: which ENGINE actually answers a given call --
the legacy in-process ``ai_editor`` path, the new engine through
:class:`adapter.mcp_adapter.MCPAdapter`, or both at once through
:class:`adapter.comparison.ComparisonMode`. ``comparison.py`` already owns *whether a call
that is running in comparison mode gets compared at all*
(:class:`adapter.comparison.EnablementStrategy`, its own per-command and sampling knobs);
this module is the narrower, upstream decision of which of the three modes a call runs
under in the first place. It does not duplicate that strategy and does not call any
engine itself -- callers read the mode this module hands back and dispatch accordingly.

This module imports nothing from ``ai_editor``, ``mcp_proxy``, ``code_analysis_server``,
or the ``tree_engine`` core: it is pure configuration plumbing, read once and queried
many times, with no engine calls, no I/O beyond that one startup read, and no side
effects on any later query.

Configuration precedence, highest first:

1. ``AI_EDITOR_FEATURE_FLAG`` -- inline JSON in the environment. This is the rollback
   lever: an operator changes this one variable and restarts the process -- no code
   change, no file touched, no redeploy of anything but the process itself.
2. ``AI_EDITOR_FEATURE_FLAG_FILE`` -- path to a JSON file with the same shape, for a
   configuration checked into a deploy artifact rather than passed as raw environment
   text. Used only when the inline variable is entirely absent.
3. The in-process default: legacy mode, no overrides -- applied only when NEITHER of the
   above is set. Legacy is the default because it is the already-proven path AI Editor
   ran before this migration existed; an unconfigured process must reproduce today's
   behavior exactly, never silently opt a fresh deployment into the new engine or into
   comparison traffic.

Granularity: a JSON payload has two keys. ``default_mode`` is the global fallback.
``overrides`` maps a key to a mode, and a key is either a bare command name
(``"universal_file_search"``, applies to that command in every format) or a
``"<command>:<format_id>"`` composite (``"universal_file_search:python"``, applies only
when that command resolves to that format). The composite is tried first, then the bare
command name, then ``default_mode`` -- so global, per-command and per-format all live in
one mapping without three separate schemas.

A value that IS set but is malformed -- invalid JSON, a non-object payload, an unknown
top-level key, a mode string outside {"legacy", "adapter", "comparison"} -- raises
:class:`FeatureFlagConfigError` immediately. Nothing here ever falls back silently to a
default on a bad value: only the genuine ABSENCE of both environment variables reaches
the default.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

__all__ = [
    "FeatureFlagMode", "FeatureFlagConfig", "FeatureFlagConfigError",
    "ENV_INLINE", "ENV_FILE", "DEFAULT_MODE",
    "load_config", "initialize", "current_config", "reset",
    "effective_mode", "should_run",
]


class FeatureFlagMode(str, Enum):
    """The three ways a command can be served."""

    LEGACY = "legacy"
    ADAPTER = "adapter"
    COMPARISON = "comparison"


class FeatureFlagConfigError(Exception):
    """Configuration that could not be trusted. Absence is fine (the default applies);
    a value that is present but wrong is never guessed at -- it is reported instead."""

    def __init__(self, message: str, **details: object) -> None:
        self.details: Mapping[str, object] = dict(details)
        super().__init__(message)


@dataclass(frozen=True)
class FeatureFlagConfig:
    """One resolved configuration: where it came from, the global mode, and the
    command/format override mapping (see module docstring for the key shape)."""

    source: str
    default_mode: FeatureFlagMode
    overrides: Mapping[str, FeatureFlagMode] = field(default_factory=dict)


#: Highest-precedence source: inline JSON payload in the environment (the rollback lever).
ENV_INLINE = "AI_EDITOR_FEATURE_FLAG"

#: Second source: a path to a JSON file with the same shape as the inline payload.
ENV_FILE = "AI_EDITOR_FEATURE_FLAG_FILE"

#: The safe in-process default when neither environment variable is set.
DEFAULT_MODE = FeatureFlagMode.LEGACY

_ALLOWED_KEYS = frozenset({"default_mode", "overrides"})


def _parse_mode(raw: object, *, where: str) -> FeatureFlagMode:
    """``raw`` -> :class:`FeatureFlagMode`, or a loud, located
    :class:`FeatureFlagConfigError` -- never a silent fallback."""
    if not isinstance(raw, str):
        raise FeatureFlagConfigError(
            f"{where}: mode must be a string, got {type(raw).__name__}", where=where, value=raw)
    try:
        return FeatureFlagMode(raw)
    except ValueError:
        valid = ", ".join(mode.value for mode in FeatureFlagMode)
        raise FeatureFlagConfigError(
            f"{where}: unknown mode {raw!r}, expected one of: {valid}",
            where=where, value=raw) from None


def _parse_payload(raw_text: str, *, source: str) -> FeatureFlagConfig:
    """Parse a JSON payload into a :class:`FeatureFlagConfig`, or raise
    :class:`FeatureFlagConfigError` naming exactly what is wrong and where."""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise FeatureFlagConfigError(
            f"{source}: invalid JSON ({exc.msg} at line {exc.lineno}, col {exc.colno})",
            source=source) from exc
    if not isinstance(payload, dict):
        raise FeatureFlagConfigError(
            f"{source}: config must be a JSON object, got {type(payload).__name__}",
            source=source)
    unknown = set(payload) - _ALLOWED_KEYS
    if unknown:
        raise FeatureFlagConfigError(
            f"{source}: unknown key(s) {sorted(unknown)}, allowed: {sorted(_ALLOWED_KEYS)}",
            source=source, unknown_keys=sorted(unknown))
    default_raw = payload.get("default_mode")
    default_mode = (DEFAULT_MODE if default_raw is None
                    else _parse_mode(default_raw, where=f"{source}: default_mode"))
    overrides_raw = payload.get("overrides", {})
    if not isinstance(overrides_raw, dict):
        raise FeatureFlagConfigError(
            f"{source}: overrides must be a JSON object, got {type(overrides_raw).__name__}",
            source=source)
    overrides = {str(key): _parse_mode(mode, where=f"{source}: overrides[{key!r}]")
                for key, mode in overrides_raw.items()}
    return FeatureFlagConfig(source=source, default_mode=default_mode, overrides=overrides)


def load_config(env: Optional[Mapping[str, str]] = None) -> FeatureFlagConfig:
    """Resolve one :class:`FeatureFlagConfig` from ``env`` (``os.environ`` if omitted),
    following the precedence documented at module level. Pure: no caching, no mutation
    -- :func:`initialize` is the layer that reads this once and remembers it."""
    source_env = os.environ if env is None else env
    inline = source_env.get(ENV_INLINE)
    if inline is not None:
        return _parse_payload(inline, source=f"env:{ENV_INLINE}")
    file_path = source_env.get(ENV_FILE)
    if file_path is not None:
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise FeatureFlagConfigError(
                f"env:{ENV_FILE}={file_path!r}: could not read config file: {exc}",
                path=file_path) from exc
        return _parse_payload(text, source=f"file:{file_path}")
    return FeatureFlagConfig(source="in-process-default", default_mode=DEFAULT_MODE, overrides={})


_lock = threading.Lock()
_config: Optional[FeatureFlagConfig] = None


def initialize(env: Optional[Mapping[str, str]] = None, *, force: bool = False) -> FeatureFlagConfig:
    """Read configuration once and cache it -- the one place this module performs I/O.
    Subsequent :func:`current_config`/:func:`effective_mode`/:func:`should_run` calls
    never touch the environment or disk again. ``force=True`` re-reads explicitly; it is
    for tests and an operator-triggered reload, never for an ordinary query."""
    global _config
    with _lock:
        if _config is None or force:
            _config = load_config(env)
        return _config


def current_config() -> FeatureFlagConfig:
    """The cached configuration, initializing it from the process environment on first
    use. No later call performs I/O: it only ever reads the cached value."""
    with _lock:
        if _config is not None:
            return _config
    return initialize()


def reset() -> None:
    """Drop the cached configuration so the next query re-initializes from the
    environment. A test-only escape hatch; ordinary call sites never need it."""
    global _config
    with _lock:
        _config = None


def effective_mode(command: str, format_id: Optional[str] = None, *,
                   config: Optional[FeatureFlagConfig] = None) -> FeatureFlagMode:
    """The mode ``command`` runs under: the ``"<command>:<format_id>"`` override if one
    is configured and ``format_id`` is known, else the bare-command override, else the
    configured (or default) global mode. Performs no I/O -- ``config`` defaults to the
    already-initialized :func:`current_config`."""
    cfg = current_config() if config is None else config
    if format_id is not None:
        composite = f"{command}:{format_id}"
        if composite in cfg.overrides:
            return cfg.overrides[composite]
    return cfg.overrides.get(command, cfg.default_mode)


def should_run(command: str, mode: FeatureFlagMode, format_id: Optional[str] = None, *,
              config: Optional[FeatureFlagConfig] = None) -> bool:
    """Whether ``command`` (optionally narrowed to ``format_id``) is routed to ``mode``
    under the effective configuration."""
    return effective_mode(command, format_id, config=config) == mode
