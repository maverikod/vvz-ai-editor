"""
Configuration placeholders resolved from environment at load/validate time.

Placeholders use ``${ENV_VAR}`` syntax inside JSON string values. Values are
substituted after ``load_dotenv_near_config`` and before adapter validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from mcp_proxy_adapter.core.config.simple_config import SimpleConfig, SimpleConfigModel

# Environment variable names
ENV_ADVERTISED_HOST = "AI_EDITOR_ADVERTISED_HOST"
ENV_REGISTRATION_HOST = "AI_EDITOR_REGISTRATION_HOST"
ENV_REGISTRATION_PORT = "AI_EDITOR_REGISTRATION_PORT"
ENV_CODE_ANALYSIS_HOST = "AI_EDITOR_CODE_ANALYSIS_HOST"
ENV_CODE_ANALYSIS_PORT = "AI_EDITOR_CODE_ANALYSIS_PORT"

# Placeholder tokens stored in config.json templates
PH_ADVERTISED_HOST = f"${{{ENV_ADVERTISED_HOST}}}"
PH_REGISTRATION_HOST = f"${{{ENV_REGISTRATION_HOST}}}"
PH_REGISTRATION_PORT = f"${{{ENV_REGISTRATION_PORT}}}"
PH_CODE_ANALYSIS_HOST = f"${{{ENV_CODE_ANALYSIS_HOST}}}"
PH_CODE_ANALYSIS_PORT = f"${{{ENV_CODE_ANALYSIS_PORT}}}"

DEFAULT_REGISTRATION_PORT = "3004"
DEFAULT_CODE_ANALYSIS_PORT = "15010"

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

_ENV_DEFAULTS: Dict[str, str] = {
    ENV_REGISTRATION_PORT: DEFAULT_REGISTRATION_PORT,
    ENV_CODE_ANALYSIS_PORT: DEFAULT_CODE_ANALYSIS_PORT,
}


@dataclass(frozen=True)
class UnresolvedPlaceholder:
    """One ``${VAR}`` that could not be resolved from the environment."""

    name: str

    @property
    def token(self) -> str:
        return f"${{{self.name}}}"


def build_registration_urls(*, protocol: str = "https") -> tuple[str, str, str]:
    """Build registration URLs with host/port placeholders."""
    scheme = "https" if protocol in ("https", "mtls") else "http"
    base = f"{scheme}://{PH_REGISTRATION_HOST}:{PH_REGISTRATION_PORT}"
    return (
        f"{base}/register",
        f"{base}/unregister",
        f"{base}/proxy/heartbeat",
    )


def contains_placeholder(value: Any) -> bool:
    """Return True when *value* is a string containing ``${...}``."""
    return isinstance(value, str) and _PLACEHOLDER_RE.search(value) is not None


def find_unresolved_placeholders(value: Any) -> list[str]:
    """Collect placeholder variable names still present in *value*."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.findall(value)
    if isinstance(value, Mapping):
        found: list[str] = []
        for item in value.values():
            found.extend(find_unresolved_placeholders(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(find_unresolved_placeholders(item))
        return found
    return []


def _resolve_string(
    text: str,
    env: Mapping[str, str],
    defaults: Mapping[str, str],
) -> tuple[str, list[UnresolvedPlaceholder]]:
    unresolved: list[UnresolvedPlaceholder] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        raw = env.get(name)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
        if name in defaults:
            return str(defaults[name])
        unresolved.append(UnresolvedPlaceholder(name))
        return match.group(0)

    return _PLACEHOLDER_RE.sub(repl, text), unresolved


def resolve_config_placeholders(
    config_data: Mapping[str, Any],
    *,
    environ: Optional[Mapping[str, str]] = None,
    defaults: Optional[Mapping[str, str]] = None,
) -> tuple[Dict[str, Any], list[UnresolvedPlaceholder]]:
    """
    Deep-copy *config_data* and substitute ``${ENV}`` tokens from *environ*.

    Returns:
        (resolved_dict, unresolved_placeholders)
    """
    env = dict(environ if environ is not None else os.environ)
    merged_defaults = dict(_ENV_DEFAULTS)
    if defaults:
        merged_defaults.update(defaults)
    all_unresolved: list[UnresolvedPlaceholder] = []

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            resolved, missing = _resolve_string(node, env, merged_defaults)
            all_unresolved.extend(missing)
            return resolved
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, Mapping):
            return {key: walk(value) for key, value in node.items()}
        return node

    resolved = walk(dict(config_data))
    assert isinstance(resolved, dict)
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[UnresolvedPlaceholder] = []
    for item in all_unresolved:
        if item.name not in seen:
            seen.add(item.name)
            unique.append(item)
    return resolved, unique


def _directory_is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def writable_config_scratch_dir(config_path: Path) -> Path:
    """
    Pick a writable directory for short-lived resolved-config JSON files.

    The real config file may live on a read-only mount (Debian ``conffile`` under
    ``/etc``). Adapter validation still resolves relative SSL paths against
    ``config_path``'s parent; only the temporary JSON body is written elsewhere.
    """
    resolved_path = config_path.resolve()
    env_dir = (os.environ.get("AI_EDITOR_CONFIG_CACHE_DIR") or "").strip()
    candidates: list[Path] = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(resolved_path.parent)
    candidates.extend(
        [
            Path("/var/ai-editor"),
            Path("/var/log/ai-editor"),
            Path("/var/lib/ai-editor"),
            Path(tempfile.gettempdir()),
        ]
    )
    seen: set[Path] = set()
    for directory in candidates:
        key = directory.resolve()
        if key in seen:
            continue
        seen.add(key)
        if _directory_is_writable(key):
            return key
    raise OSError(
        f"No writable directory for config resolution cache (config={resolved_path})"
    )


def load_simple_config_model(
    config_path: Path,
    content: Mapping[str, Any],
) -> SimpleConfigModel:
    """
    Load adapter ``SimpleConfigModel`` from an in-memory dict.

    Uses a short-lived file in a writable cache directory. Relative SSL paths in
    validation still resolve against the real config directory (see
    ``SimpleConfigValidator(str(config_path))``).
    """
    resolved_path = config_path.resolve()
    cache_dir = writable_config_scratch_dir(resolved_path)
    path_key = hashlib.sha256(str(resolved_path).encode()).hexdigest()[:12]
    tmp = cache_dir / f".{resolved_path.name}.{path_key}.resolved.json"
    tmp.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    try:
        return SimpleConfig(str(tmp)).load()
    finally:
        tmp.unlink(missing_ok=True)


def load_resolved_simple_config(
    config_path: Path,
    content: Mapping[str, Any],
) -> SimpleConfig:
    """Return ``SimpleConfig`` with model loaded from resolved *content*."""
    simple = SimpleConfig(str(config_path.resolve()))
    simple.model = load_simple_config_model(config_path, content)
    return simple
