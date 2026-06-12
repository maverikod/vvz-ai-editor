"""Tests for code_analysis_server → code-analysis-client config bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.core.exceptions import ValidationError
from ai_editor.core.upstream.ca_config_bridge import (
    build_jsonrpc_kwargs_from_ca_section,
    ca_section_to_adapter_settings,
    load_resolved_ca_section,
)


def test_ca_section_to_adapter_settings_https_mtls() -> None:
    section = {
        "host": "10.0.0.5",
        "port": 15010,
        "protocol": "https",
        "ssl": {
            "cert": "/tmp/client.crt",
            "key": "/tmp/client.key",
            "ca": "/tmp/ca.crt",
        },
    }
    settings = ca_section_to_adapter_settings(section)
    assert settings["host"] == "10.0.0.5"
    assert settings["port"] == 15010
    assert settings["protocol"] == "https"
    assert settings["ssl"]["cert"] == "/tmp/client.crt"
    assert settings["ssl"]["key"] == "/tmp/client.key"


def test_build_jsonrpc_kwargs_expands_ssl_paths(tmp_path: Path) -> None:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    ca.write_text("ca", encoding="utf-8")

    section = {
        "host": "127.0.0.1",
        "port": 15001,
        "protocol": "https",
        "timeout": 30.0,
        "check_hostname": True,
        "ssl": {"cert": str(cert), "key": str(key), "ca": str(ca)},
    }
    kwargs = build_jsonrpc_kwargs_from_ca_section(section)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 15001
    assert kwargs["timeout"] == 30.0
    assert kwargs["check_hostname"] is True
    assert kwargs["cert"] == str(cert.resolve())
    assert kwargs["key"] == str(key.resolve())
    assert kwargs["ca"] == str(ca.resolve())


def test_load_resolved_ca_section_missing_section(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"server": {"host": "127.0.0.1"}}), encoding="utf-8")
    with pytest.raises(ValidationError, match="code_analysis_server"):
        load_resolved_ca_section(cfg)


def test_load_resolved_ca_section_resolves_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "code_analysis_server": {
                    "host": "${AI_EDITOR_CODE_ANALYSIS_HOST}",
                    "port": 15010,
                    "protocol": "https",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_EDITOR_CODE_ANALYSIS_HOST", "ca.example.test")
    section = load_resolved_ca_section(cfg)
    assert section["host"] == "ca.example.test"
    assert section["server_id"] == "code-analysis-server"
