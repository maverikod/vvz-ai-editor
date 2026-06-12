#!/usr/bin/env python3
"""
Host-side config preflight for ai-editor-docker (no ai_editor package required).

Verifies that ${AI_EDITOR_*} placeholders in the service config can be resolved
from the process environment before the Docker container is started.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

_ENV_DEFAULTS: dict[str, str] = {
    "AI_EDITOR_REGISTRATION_PORT": "3004",
    "AI_EDITOR_CODE_ANALYSIS_PORT": "15010",
}

_REQUIRED_FOR_AI_EDITOR: frozenset[str] = frozenset(
    {
        "AI_EDITOR_ADVERTISED_HOST",
        "AI_EDITOR_REGISTRATION_HOST",
        "AI_EDITOR_CODE_ANALYSIS_HOST",
    }
)


def _collect_placeholder_names(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(_PLACEHOLDER_RE.findall(value))
    elif isinstance(value, Mapping):
        for item in value.values():
            found.update(_collect_placeholder_names(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_placeholder_names(item))
    return found


def _resolve_string(
    text: str,
    env: Mapping[str, str],
    defaults: Mapping[str, str],
) -> tuple[str, list[str]]:
    errors: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        raw = env.get(name)
        if raw is not None and str(raw).strip():
            value = str(raw).strip()
            if _PLACEHOLDER_RE.search(value):
                errors.append(
                    f"environment variable {name} still contains a placeholder: {value!r}"
                )
                return match.group(0)
            return value
        if name in defaults:
            return str(defaults[name])
        errors.append(
            f"unset environment variable {name} required by config placeholder ${{{name}}}"
        )
        return match.group(0)

    resolved = _PLACEHOLDER_RE.sub(repl, text)
    return resolved, errors


def _resolve_node(value: Any, env: Mapping[str, str]) -> tuple[Any, list[str]]:
    if isinstance(value, str):
        return _resolve_string(value, env, _ENV_DEFAULTS)
    if isinstance(value, list):
        errors: list[str] = []
        out = []
        for item in value:
            resolved_item, item_errors = _resolve_node(item, env)
            out.append(resolved_item)
            errors.extend(item_errors)
        return out, errors
    if isinstance(value, Mapping):
        errors = []
        out: dict[str, Any] = {}
        for key, item in value.items():
            resolved_item, item_errors = _resolve_node(item, env)
            out[key] = resolved_item
            errors.extend(item_errors)
        return out, errors
    return value, []


def check_config_placeholders(
    config_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Return error messages; empty list means placeholders are ready."""
    env = dict(environ if environ is not None else os.environ)
    errors: list[str] = []

    if not config_path.is_file():
        return [f"configuration file not found: {config_path}"]

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON in {config_path}: {exc}"]

    referenced = _collect_placeholder_names(raw)
    if not referenced:
        return []

    for name in sorted(_REQUIRED_FOR_AI_EDITOR & referenced):
        if name not in env or not str(env.get(name, "")).strip():
            if name not in _ENV_DEFAULTS:
                errors.append(
                    f"required variable {name} is not set in /etc/default/ai-editor "
                    f"or the service environment"
                )

    _resolved, resolve_errors = _resolve_node(raw, env)
    errors.extend(resolve_errors)

    remaining = _collect_placeholder_names(_resolved)
    for name in sorted(remaining):
        token = f"${{{name}}}"
        errors.append(
            f"placeholder {token} is still present after environment substitution"
        )

    return _unique(errors)


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    config_path = Path(
        args[0]
        if args
        else os.environ.get(
            "AI_EDITOR_CONFIG_PATH",
            "/etc/ai-editor/ai_editor_container.json",
        )
    )
    errors = check_config_placeholders(config_path)
    if errors:
        print("[ai-editor-config] Configuration is not ready to start:", file=sys.stderr)
        for err in errors:
            print(f"[ai-editor-config]   - {err}", file=sys.stderr)
        print(
            "[ai-editor-config] Edit /etc/default/ai-editor, install mTLS certs, then run:",
            file=sys.stderr,
        )
        print(
            "[ai-editor-config]   sudo /usr/lib/ai-editor/config-preflight.sh",
            file=sys.stderr,
        )
        print(
            "[ai-editor-config]   sudo ai-editor-docker recreate",
            file=sys.stderr,
        )
        return 1

    print(f"[ai-editor-config] Placeholders resolved for {config_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
