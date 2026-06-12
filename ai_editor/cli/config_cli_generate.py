"""
Generate command for config CLI (file-editing server).

Wraps mcp-proxy-adapter SimpleConfigGenerator, then merges editor extension sections.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
from mcp_proxy_adapter.core.config.simple_config_generator import SimpleConfigGenerator

from ai_editor.core.config_placeholders import (
    PH_ADVERTISED_HOST,
    PH_CODE_ANALYSIS_HOST,
    PH_REGISTRATION_HOST,
)
from ai_editor.core.config_validation import validate_config_file
from ai_editor.core.editor_config_extension import (
    DEFAULT_AI_EDITOR_LOG,
    DEFAULT_CA_SERVER_ID,
    DEFAULT_CA_TIMEOUT,
    DEFAULT_WORKSPACE_ROOT,
    build_ai_editor_section,
    build_code_analysis_server_section,
    merge_editor_extensions,
)


def _resolve_ssl_triplet(
    args: argparse.Namespace,
    *,
    cert_attr: str,
    key_attr: str,
    ca_attr: str,
    fallbacks: tuple[Optional[str], Optional[str], Optional[str]],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    cert = getattr(args, cert_attr, None) or fallbacks[0]
    key = getattr(args, key_attr, None) or fallbacks[1]
    ca = getattr(args, ca_attr, None) or fallbacks[2]
    return cert, key, ca


def _build_extension_sections(
    args: argparse.Namespace,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    server_port = args.server_port
    if server_port is None:
        server_port = 8443 if args.protocol in ("https", "mtls") else 8080

    reg_cert, reg_key, reg_ca = _resolve_ssl_triplet(
        args,
        cert_attr="registration_cert_file",
        key_attr="registration_key_file",
        ca_attr="registration_ca_cert_file",
        fallbacks=(None, None, None),
    )
    srv_cert, srv_key, srv_ca = _resolve_ssl_triplet(
        args,
        cert_attr="server_cert_file",
        key_attr="server_key_file",
        ca_attr="server_ca_cert_file",
        fallbacks=(None, None, None),
    )
    ca_cert, ca_key, ca_ca = _resolve_ssl_triplet(
        args,
        cert_attr="code_analysis_cert_file",
        key_attr="code_analysis_key_file",
        ca_attr="code_analysis_ca_cert_file",
        fallbacks=(reg_cert or srv_cert, reg_key or srv_key, reg_ca or srv_ca),
    )

    ca_protocol = getattr(args, "code_analysis_protocol", None) or "https"
    code_analysis = build_code_analysis_server_section(
        host=args.code_analysis_host,
        port=args.code_analysis_port,
        protocol=ca_protocol,
        timeout=getattr(args, "code_analysis_timeout", DEFAULT_CA_TIMEOUT),
        server_id=getattr(args, "code_analysis_server_id", DEFAULT_CA_SERVER_ID),
        cert_file=ca_cert,
        key_file=ca_key,
        ca_cert_file=ca_ca,
        crl_file=getattr(args, "code_analysis_crl_file", None),
        check_hostname=bool(getattr(args, "code_analysis_check_hostname", False)),
    )

    ai_editor = build_ai_editor_section(
        server_host=args.server_host or "0.0.0.0",
        server_port=server_port,
        workspace_root=getattr(
            args, "ai_editor_workspace_root", DEFAULT_WORKSPACE_ROOT
        ),
        log_path=getattr(args, "ai_editor_log", DEFAULT_AI_EDITOR_LOG),
        git_commit_on_write=not getattr(
            args, "ai_editor_no_git_commit_on_write", False
        ),
    )
    return code_analysis, ai_editor


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate config via adapter generator + editor extension merge."""
    out_path = Path(getattr(args, "out", None) or "config.json").expanduser()
    reg_protocol = getattr(args, "registration_protocol", None) or args.protocol

    server_port = args.server_port
    if server_port is None:
        server_port = 8443 if args.protocol in ("https", "mtls") else 8080

    queue_enabled = getattr(args, "queue_enabled", True) and not getattr(
        args, "queue_disabled", False
    )
    queue_in_memory = getattr(args, "queue_in_memory", True) and not getattr(
        args, "queue_persistent", False
    )

    try:
        generator = SimpleConfigGenerator()
        generator.generate(
            protocol=args.protocol,
            with_proxy=bool(getattr(args, "with_proxy", False)),
            out_path=str(out_path),
            server_host=args.server_host,
            server_port=server_port,
            server_cert_file=getattr(args, "server_cert_file", None),
            server_key_file=getattr(args, "server_key_file", None),
            server_ca_cert_file=getattr(args, "server_ca_cert_file", None),
            server_crl_file=getattr(args, "server_crl_file", None),
            server_debug=getattr(args, "server_debug", False) or None,
            server_log_level=getattr(args, "server_log_level", None),
            server_log_dir=getattr(args, "server_log_dir", None),
            registration_host=getattr(args, "registration_host", None)
            or PH_REGISTRATION_HOST,
            registration_port=getattr(args, "registration_port", None),
            registration_protocol=reg_protocol,
            registration_cert_file=getattr(args, "registration_cert_file", None),
            registration_key_file=getattr(args, "registration_key_file", None),
            registration_ca_cert_file=getattr(args, "registration_ca_cert_file", None),
            registration_crl_file=getattr(args, "registration_crl_file", None),
            registration_server_id=getattr(args, "registration_server_id", None),
            registration_server_name=getattr(args, "registration_server_name", None),
            instance_uuid=getattr(args, "instance_uuid", None) or str(uuid.uuid4()),
        )

        raw = json.loads(out_path.read_text(encoding="utf-8"))
        ca_section, ai_section = _build_extension_sections(args)
        advertised = getattr(args, "server_advertised_host", None) or PH_ADVERTISED_HOST
        merged = merge_editor_extensions(
            raw,
            code_analysis_server=ca_section,
            ai_editor=ai_section,
            enable_qa_mcp_hooks=bool(getattr(args, "enable_qa_mcp_hooks", False)),
            advertised_host=advertised,
            registration_protocol=reg_protocol,
        )

        out_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        cfg = SimpleConfig(str(out_path))
        model = cfg.load()
        if model is None:
            raise RuntimeError("Adapter config load returned no model")
        model.queue_manager.enabled = queue_enabled
        model.queue_manager.in_memory = queue_in_memory
        if getattr(args, "queue_max_concurrent", None) is not None:
            model.queue_manager.max_concurrent_jobs = args.queue_max_concurrent
        if getattr(args, "queue_retention_seconds", None) is not None:
            model.queue_manager.completed_job_retention_seconds = (
                args.queue_retention_seconds
            )
        cfg.save()

        # Re-merge editor sections after adapter save (save writes adapter sections only)
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        saved = merge_editor_extensions(
            saved,
            code_analysis_server=ca_section,
            ai_editor=ai_section,
            enable_qa_mcp_hooks=bool(getattr(args, "enable_qa_mcp_hooks", False)),
            advertised_host=advertised,
            registration_protocol=reg_protocol,
        )
        out_path.write_text(
            json.dumps(saved, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(f"✅ Configuration generated: {out_path.resolve()}")

        if not getattr(args, "no_validate", False):
            return validate_config_file(out_path)
        return 0
    except Exception as exc:
        print(f"❌ Error generating configuration: {exc}", file=sys.stderr)
        return 1
