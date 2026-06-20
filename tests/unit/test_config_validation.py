"""
Unit tests for config validation wrapper (adapter + editor extensions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.core.config_placeholders import (
    ENV_ADVERTISED_HOST,
    ENV_CODE_ANALYSIS_HOST,
    ENV_REGISTRATION_HOST,
)
from ai_editor.core.config_validation import (
    collect_config_validation_issues,
    validate_config_file,
)
from ai_editor.core.editor_config_extension import (
    LEGACY_CA_HOST,
    LEGACY_CA_PORT,
    build_ai_editor_section,
    build_code_analysis_server_section,
    merge_editor_extensions,
)
from tests.test_config_driver_helpers import create_dummy_ssl_certs_in_dir


def _minimal_adapter_config(
    tmp_path: Path,
    *,
    protocol: str = "http",
    with_ssl: bool = False,
) -> dict:
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    if with_ssl:
        create_dummy_ssl_certs_in_dir(cert_dir)

    server: dict = {
        "host": "0.0.0.0",
        "port": 8080 if protocol == "http" else 8443,
        "protocol": protocol,
        "servername": "localhost",
        "debug": False,
        "log_level": "INFO",
        "log_dir": str(tmp_path / "logs"),
    }
    if protocol in ("https", "mtls"):
        server["ssl"] = {
            "cert": str(cert_dir / "server.crt"),
            "key": str(cert_dir / "server.key"),
            "ca": str(cert_dir / "ca.crt"),
            "crl": None,
            "dnscheck": False,
            "check_hostname": False,
        }

    return {
        "server": server,
        "client": {"enabled": False, "protocol": protocol, "ssl": None},
        "registration": {
            "enabled": False,
            "protocol": "http",
            "register_url": "http://localhost:3005/register",
            "unregister_url": "http://localhost:3005/unregister",
            "heartbeat_interval": 30,
            "server_id": "ai-editor-server",
            "server_name": "AI Editor Server",
            "metadata": {},
            "instance_uuid": "00000000-0000-4000-8000-000000000001",
            "auto_on_startup": False,
            "auto_on_shutdown": False,
            "ssl": None,
            "heartbeat": {
                "url": "http://localhost:3005/proxy/heartbeat",
                "interval": 30,
            },
        },
        "auth": {"use_token": False, "use_roles": False, "tokens": {}, "roles": {}},
        "queue_manager": {
            "enabled": True,
            "in_memory": True,
            "registry_path": None,
            "shutdown_timeout": 30.0,
            "max_concurrent_jobs": 5,
            "max_queue_size": None,
            "per_job_type_limits": None,
            "completed_job_retention_seconds": 21600,
        },
    }


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_missing_code_analysis_server_is_error(tmp_path: Path) -> None:
    cfg = _minimal_adapter_config(tmp_path)
    cfg["ai_editor"] = build_ai_editor_section(server_host="0.0.0.0", server_port=8080)
    path = _write_config(tmp_path, cfg)

    issues, _ = collect_config_validation_issues(path)
    errors = [i for i in issues if i.level == "error"]
    assert any("code_analysis_server" in i.message for i in errors)


def test_legacy_ca_endpoint_rejected(tmp_path: Path) -> None:
    cfg = _minimal_adapter_config(tmp_path)
    cfg["code_analysis_server"] = build_code_analysis_server_section(
        host=LEGACY_CA_HOST,
        port=LEGACY_CA_PORT,
        protocol="http",
    )
    cfg["ai_editor"] = build_ai_editor_section(server_host="0.0.0.0", server_port=8080)
    path = _write_config(tmp_path, cfg)

    issues, _ = collect_config_validation_issues(path)
    errors = [i for i in issues if i.level == "error"]
    assert any("legacy default" in i.message for i in errors)


def test_legacy_ca_port_rejected(tmp_path: Path) -> None:
    cfg = _minimal_adapter_config(tmp_path)
    cfg["code_analysis_server"] = build_code_analysis_server_section(
        host="code-analysis-server",
        port=LEGACY_CA_PORT,
        protocol="http",
    )
    cfg["ai_editor"] = build_ai_editor_section(server_host="0.0.0.0", server_port=8080)
    path = _write_config(tmp_path, cfg)

    issues, _ = collect_config_validation_issues(path)
    errors = [i for i in issues if i.level == "error"]
    assert any("legacy 15001" in i.message for i in errors)


def test_valid_http_config_passes(tmp_path: Path) -> None:
    cfg = _minimal_adapter_config(tmp_path)
    cfg = merge_editor_extensions(
        cfg,
        code_analysis_server=build_code_analysis_server_section(
            host="127.0.0.1",
            port=15010,
            protocol="http",
        ),
        ai_editor=build_ai_editor_section(server_host="0.0.0.0", server_port=8080),
        use_network_placeholders=False,
    )
    path = _write_config(tmp_path, cfg)

    assert validate_config_file(path) == 0


def test_https_ca_requires_ssl_files(tmp_path: Path) -> None:
    cfg = _minimal_adapter_config(tmp_path, protocol="http")
    cfg = merge_editor_extensions(
        cfg,
        code_analysis_server=build_code_analysis_server_section(
            host="127.0.0.1",
            port=15010,
            protocol="https",
            cert_file="/nonexistent/client.crt",
            key_file="/nonexistent/client.key",
            ca_cert_file="/nonexistent/ca.crt",
        ),
        ai_editor=build_ai_editor_section(server_host="0.0.0.0", server_port=8080),
    )
    path = _write_config(tmp_path, cfg)

    issues, _ = collect_config_validation_issues(path)
    errors = [i for i in issues if i.level == "error"]
    assert errors


def test_generate_cli_produces_valid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cert_dir = tmp_path / "certs"
    create_dummy_ssl_certs_in_dir(cert_dir)

    monkeypatch.setenv(ENV_ADVERTISED_HOST, "127.0.0.1")
    monkeypatch.setenv(ENV_REGISTRATION_HOST, "127.0.0.1")
    monkeypatch.setenv(ENV_CODE_ANALYSIS_HOST, "127.0.0.1")

    from ai_editor.cli.config_cli_generate import cmd_generate
    import argparse

    args = argparse.Namespace(
        protocol="http",
        out=str(tmp_path / "config.json"),
        with_proxy=False,
        server_host="0.0.0.0",
        server_port=8080,
        server_cert_file=None,
        server_key_file=None,
        server_ca_cert_file=None,
        server_crl_file=None,
        server_debug=False,
        server_log_level=None,
        server_log_dir=str(tmp_path / "logs"),
        registration_host=None,
        registration_port=None,
        registration_protocol=None,
        registration_cert_file=None,
        registration_key_file=None,
        registration_ca_cert_file=None,
        registration_crl_file=None,
        registration_server_id=None,
        registration_server_name=None,
        instance_uuid="00000000-0000-4000-8000-000000000002",
        server_advertised_host=None,
        enable_qa_mcp_hooks=False,
        no_validate=False,
        code_analysis_host="127.0.0.1",
        code_analysis_port=15010,
        code_analysis_protocol="http",
        code_analysis_timeout=60.0,
        code_analysis_server_id="code-analysis-server",
        code_analysis_cert_file=None,
        code_analysis_key_file=None,
        code_analysis_ca_cert_file=None,
        code_analysis_crl_file=None,
        code_analysis_check_hostname=False,
        ai_editor_workspace_root="data/editor_workspaces",
        ai_editor_no_git_commit_on_write=False,
        queue_enabled=True,
        queue_disabled=False,
        queue_in_memory=True,
        queue_persistent=False,
        queue_max_concurrent=None,
        queue_retention_seconds=None,
    )

    assert cmd_generate(args) == 0
    generated = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert generated["code_analysis_server"]["host"] == "127.0.0.1"
    assert "${" not in generated["server"]["advertised_host"]
    assert (
        generated["ai_editor"]["storage"]["workspace_root"] == "data/editor_workspaces"
    )
