"""
Unit tests for config placeholder resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai_editor.core.config_placeholders import (
    ENV_ADVERTISED_HOST,
    ENV_CODE_ANALYSIS_HOST,
    ENV_REGISTRATION_HOST,
    ENV_REGISTRATION_PORT,
    PH_ADVERTISED_HOST,
    PH_CODE_ANALYSIS_HOST,
    PH_REGISTRATION_HOST,
    build_registration_urls,
    load_simple_config_model,
    resolve_config_placeholders,
    writable_config_scratch_dir,
)


def test_resolve_embedded_placeholders() -> None:
    raw = {
        "server": {"advertised_host": PH_ADVERTISED_HOST},
        "registration": {
            "register_url": build_registration_urls()[0],
        },
        "code_analysis_server": {"host": PH_CODE_ANALYSIS_HOST, "port": 15010},
    }
    env = {
        ENV_ADVERTISED_HOST: "10.0.0.1",
        ENV_REGISTRATION_HOST: "mcp-proxy",
        ENV_REGISTRATION_PORT: "3004",
        ENV_CODE_ANALYSIS_HOST: "ca-host",
    }
    resolved, unresolved = resolve_config_placeholders(raw, environ=env)
    assert not unresolved
    assert resolved["server"]["advertised_host"] == "10.0.0.1"
    assert resolved["registration"]["register_url"] == "https://mcp-proxy:3004/register"
    assert resolved["code_analysis_server"]["host"] == "ca-host"


def test_writable_config_scratch_dir_uses_cache_when_config_dir_readonly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "etc" / "ai-editor"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "ai_editor_container.json"
    config_path.write_text("{}", encoding="utf-8")
    os.chmod(config_dir, 0o555)

    cache_dir = tmp_path / "var" / "ai-editor" / ".config-cache"
    monkeypatch.setenv("AI_EDITOR_CONFIG_CACHE_DIR", str(cache_dir))

    assert writable_config_scratch_dir(config_path) == cache_dir.resolve()
    assert cache_dir.is_dir()

    os.chmod(config_dir, 0o755)


def test_load_simple_config_model_writes_to_cache_not_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "etc" / "ai-editor"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "ai_editor_container.json"
    config_path.write_text("{}", encoding="utf-8")
    os.chmod(config_dir, 0o555)

    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("AI_EDITOR_CONFIG_CACHE_DIR", str(cache_dir))

    content = {
        "server": {
            "host": "0.0.0.0",
            "port": 15000,
            "protocol": "http",
            "servername": "test",
            "debug": False,
            "log_level": "INFO",
        },
        "client": {"enabled": False},
        "registration": {"enabled": False},
        "server_validation": {"enabled": False},
        "auth": {},
        "queue_manager": {"enabled": False},
    }
    model = load_simple_config_model(config_path, content)
    assert model.server.port == 15000
    assert list(config_dir.glob("*.resolved.json")) == []
    assert cache_dir.is_dir()

    os.chmod(config_dir, 0o755)


def test_unresolved_placeholder_reported() -> None:
    raw = {"server": {"advertised_host": PH_ADVERTISED_HOST}}
    _resolved, unresolved = resolve_config_placeholders(raw, environ={})
    assert len(unresolved) == 1
    assert unresolved[0].name == ENV_ADVERTISED_HOST


def test_container_template_resolves_with_docker_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_ADVERTISED_HOST, "ai-editor-server")
    monkeypatch.setenv(ENV_REGISTRATION_HOST, "mcp-proxy")
    monkeypatch.setenv(ENV_CODE_ANALYSIS_HOST, "code-analysis-server")
    from ai_editor.config_templates import (
        CONTAINER_TEMPLATE_NAME,
        copy_bundled_template,
    )
    from ai_editor.core.config_validation import collect_config_validation_issues

    config_path = copy_bundled_template(tmp_path, name=CONTAINER_TEMPLATE_NAME)
    issues, _ = collect_config_validation_issues(config_path)
    errors = [i for i in issues if i.level == "error"]
    ssl_missing = [e for e in errors if "file not found" in e.message]
    other = [e for e in errors if e not in ssl_missing]
    assert not other, other
