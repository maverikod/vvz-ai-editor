#!/usr/bin/env python3
"""
Settings schema and file editor for /etc/default/ai-editor (no ai_editor package).

Declares every setting the ai-editor-docker package owns, validates a proposed
value before it is written, and rewrites the settings file in place while keeping
its comments and ordering intact.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ipaddress
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

SETTINGS_FILE = Path(os.environ.get("AI_EDITOR_SETTINGS_FILE", "/etc/default/ai-editor"))

_ASSIGNMENT_RE = re.compile(r"^(?P<lead>\s*)(?P<comment>#\s*)?(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                          r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_NETWORK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_UNIXNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_SUFFIX_RE = re.compile(r"^[A-Za-z0-9._-]{0,63}$")
_SHELL_SAFE_RE = re.compile(r"^[A-Za-z0-9_./:=@,+-]*$")


class SettingError(ValueError):
    """A rejected key or value. Nothing is written when this is raised."""


@dataclass(frozen=True)
class Setting:
    """One supported setting: its CLI option, its validator and its help text."""

    key: str
    option: str
    help: str
    validate: Callable[[str], str]
    notes: list[str] = field(default_factory=list)


def _validate_port(value: str) -> str:
    if not value.isdigit():
        raise SettingError(f"not a port number: {value!r} (expected an integer 1-65535)")
    number = int(value)
    if not 1 <= number <= 65535:
        raise SettingError(f"port out of range: {value!r} (expected 1-65535)")
    return str(number)


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _validate_peer_host(value: str) -> str:
    """A peer address: a Docker DNS name is expected, an IP literal is accepted."""
    if not value:
        raise SettingError("host must not be empty")
    if _is_ip_literal(value):
        return value
    if not _HOSTNAME_RE.match(value):
        raise SettingError(f"not a DNS name or IP address: {value!r}")
    return value


def _validate_bind_host(value: str) -> str:
    if not value:
        raise SettingError("bind host must not be empty")
    if _is_ip_literal(value) or _HOSTNAME_RE.match(value):
        return value
    raise SettingError(f"not a bind address: {value!r}")


def _validate_protocol(value: str) -> str:
    allowed = ("http", "https", "mtls")
    if value not in allowed:
        raise SettingError(f"unsupported protocol {value!r} (expected one of {', '.join(allowed)})")
    return value


def _validate_client_protocol(value: str) -> str:
    """The code-analysis client section accepts only plain URL schemes."""
    allowed = ("http", "https")
    if value not in allowed:
        raise SettingError(
            f"unsupported protocol {value!r} for the code-analysis client "
            f"(expected one of {', '.join(allowed)})"
        )
    return value


def _validate_abs_path(value: str) -> str:
    if not value.startswith("/"):
        raise SettingError(f"not an absolute path: {value!r}")
    if "//" in value or value.rstrip("/") != value.rstrip("/").strip():
        raise SettingError(f"malformed path: {value!r}")
    if len(value) > 1 and value.endswith("/"):
        raise SettingError(f"path must not end with a slash: {value!r}")
    if not _SHELL_SAFE_RE.match(value):
        raise SettingError(f"path contains characters that are unsafe in a shell file: {value!r}")
    return value


def _validate_network(value: str) -> str:
    if not _NETWORK_RE.match(value):
        raise SettingError(f"not a Docker network name: {value!r}")
    return value


def _validate_dns_name(value: str) -> str:
    if _is_ip_literal(value):
        raise SettingError(
            f"{value!r} is an IP address; a Docker network alias must be a DNS name"
        )
    if not _HOSTNAME_RE.match(value):
        raise SettingError(f"not a DNS name: {value!r}")
    return value


def _validate_unixname(value: str) -> str:
    if not _UNIXNAME_RE.match(value):
        raise SettingError(f"not a valid system user or group name: {value!r}")
    return value


def _validate_suffix(value: str) -> str:
    if not _SUFFIX_RE.match(value):
        raise SettingError(f"not a valid server-id suffix: {value!r}")
    return value


_DNS_PEER_NOTE = "Docker DNS name on the primary network; an IP literal bypasses Docker DNS."

SETTINGS: tuple[Setting, ...] = (
    Setting("AI_EDITOR_PORT", "--port", "Host port published for the container.", _validate_port),
    Setting("AI_EDITOR_BIND_HOST", "--bind-host", "Address the server binds inside the container.",
            _validate_bind_host),
    Setting("AI_EDITOR_ADVERTISED_HOST", "--advertised-host",
            "Host the server advertises to peers.", _validate_peer_host, [_DNS_PEER_NOTE]),
    Setting("AI_EDITOR_PROTOCOL", "--protocol",
            "Server/client/transport protocol (http, https, mtls).", _validate_protocol),
    Setting("AI_EDITOR_REGISTRATION_HOST", "--registration-host",
            "MCP proxy host used for register/unregister/heartbeat.", _validate_peer_host,
            [_DNS_PEER_NOTE]),
    Setting("AI_EDITOR_REGISTRATION_PORT", "--registration-port", "MCP proxy port.", _validate_port),
    Setting("AI_EDITOR_REGISTRATION_PROTOCOL", "--registration-protocol",
            "Registration protocol (http, https, mtls).", _validate_protocol),
    Setting("AI_EDITOR_CODE_ANALYSIS_HOST", "--code-analysis-host",
            "Code Analysis server host.", _validate_peer_host, [_DNS_PEER_NOTE]),
    Setting("AI_EDITOR_CODE_ANALYSIS_PORT", "--code-analysis-port",
            "Code Analysis server port.", _validate_port),
    Setting("AI_EDITOR_CODE_ANALYSIS_PROTOCOL", "--code-analysis-protocol",
            "Code Analysis protocol (http, https).", _validate_client_protocol),
    Setting("AI_EDITOR_SERVER_ID_SUFFIX", "--server-id-suffix",
            "Suffix appended to registration.server_id.", _validate_suffix),
    Setting("AI_EDITOR_MTLS_DIR", "--mtls-dir",
            "Host directory holding the mTLS material.", _validate_abs_path),
    Setting("AI_EDITOR_MTLS_CONTAINER_DIR", "--mtls-container-dir",
            "Mount point of the mTLS material inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_SERVER_SSL_CERT", "--server-cert",
            "Server certificate path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_SERVER_SSL_KEY", "--server-key",
            "Server private key path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_SERVER_SSL_CA", "--server-ca",
            "Server CA bundle path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_CLIENT_SSL_CERT", "--client-cert",
            "Client certificate path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_CLIENT_SSL_KEY", "--client-key",
            "Client private key path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_CLIENT_SSL_CA", "--client-ca",
            "Client CA bundle path inside the container.", _validate_abs_path),
    Setting("AI_EDITOR_NETWORK_PRIMARY", "--network-primary",
            "Primary Docker network the container joins.", _validate_network),
    Setting("AI_EDITOR_NETWORK_SECONDARY", "--network-secondary",
            "Secondary Docker network the container joins.", _validate_network),
    Setting("AI_EDITOR_DOCKER_DNS_NAME", "--dns-name",
            "Docker network alias this service publishes itself under.", _validate_dns_name),
    Setting("AI_EDITOR_CONTAINER", "--container", "Docker container name.", _validate_network),
    Setting("AI_EDITOR_USER", "--user", "System user owning the service files.", _validate_unixname),
    Setting("AI_EDITOR_GROUP", "--group", "System group owning the service files.",
            _validate_unixname),
)

BY_KEY: Mapping[str, Setting] = {item.key: item for item in SETTINGS}
BY_OPTION: Mapping[str, Setting] = {item.option: item for item in SETTINGS}


def validate_pair(key: str, value: str) -> str:
    """Return the normalised value, or raise SettingError for an unknown/bad input."""
    setting = BY_KEY.get(key)
    if setting is None:
        raise SettingError(
            f"unknown setting {key!r}; run 'ai-editor-config list' for the supported keys"
        )
    text = value.strip()
    if text != value:
        raise SettingError(f"value for {key} has leading or trailing whitespace: {value!r}")
    if not _SHELL_SAFE_RE.match(text):
        raise SettingError(
            f"value for {key} contains characters that are unsafe in a shell settings file: {text!r}"
        )
    return setting.validate(text)


def read_settings(path: Path = SETTINGS_FILE) -> dict[str, str]:
    """Read the active (uncommented) assignments from the settings file."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ASSIGNMENT_RE.match(line)
        if match is None or match.group("comment"):
            continue
        values[match.group("key")] = match.group("value").strip().strip('"').strip("'")
    return values


def apply_settings(updates: Mapping[str, str], path: Path = SETTINGS_FILE) -> list[str]:
    """
    Write *updates* into the settings file atomically, preserving comments.

    An existing active assignment is replaced in place; a commented-out assignment is
    activated in place; anything else is appended. Returns the changed keys.
    """
    if not updates:
        return []
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    remaining = dict(updates)
    changed: list[str] = []
    seen_active: set[str] = set()

    for index, line in enumerate(lines):
        match = _ASSIGNMENT_RE.match(line)
        if match is None:
            continue
        key = match.group("key")
        if key not in remaining:
            continue
        if match.group("comment") and key in seen_active:
            continue
        new_value = remaining.pop(key)
        old_value = match.group("value").strip().strip('"').strip("'")
        lines[index] = f"{key}={new_value}"
        if match.group("comment") or old_value != new_value:
            changed.append(key)
        seen_active.add(key)

    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Added by ai-editor-config.")
        for key in sorted(remaining):
            lines.append(f"{key}={remaining[key]}")
            changed.append(key)

    body = "\n".join(lines) + "\n"
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".ai-editor.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(body)
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return changed
