"""
Persist ``project_pip_*`` subprocess stdout/stderr under the server log directory.

Writes a single UTF-8 text file per invocation (under ``<server log_dir>/project_pip/``)
so queued and direct pip runs leave durable output beside other server logs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage_paths import load_raw_config

logger = logging.getLogger(__name__)

PROJECT_PIP_LOG_SUBDIR = "project_pip"


def _resolve_active_config_path() -> Path:
    """Same resolution as BaseMCPCommand._resolve_config_path (avoid circular imports)."""
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        cfg_path = getattr(cfg, "config_path", None)
        if isinstance(cfg_path, str) and cfg_path.strip():
            return Path(cfg_path).expanduser().resolve()
    except Exception:
        pass
    return (Path.cwd() / "config.json").resolve()


def resolve_server_log_dir() -> Path:
    """
    Resolve the configured server log directory (absolute).

    Uses ``server.log_dir`` from the active config, default ``./logs``, relative paths
    resolved against the config file's directory — same rules as daemon logging.
    """
    config_path = _resolve_active_config_path()
    data = load_raw_config(config_path)
    server = data.get("server") or {}
    if not isinstance(server, dict):
        server = {}
    log_dir_str = server.get("log_dir", "./logs")
    if not isinstance(log_dir_str, str) or not log_dir_str.strip():
        log_dir_str = "./logs"
    log_dir = Path(log_dir_str).expanduser()
    if not log_dir.is_absolute():
        log_dir = (config_path.parent / log_dir).resolve()
    return log_dir.resolve()


def write_project_pip_session_log(
    *,
    command_name: str,
    project_id: str,
    pip_args: List[str],
    stdout: str,
    stderr: str,
    returncode: Optional[int],
    timed_out: bool,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write pip stdout/stderr to a session log file under the server logs directory.

    Returns a dict of fields to merge into command success payloads. On failure,
    still returns keys with ``pip_output_log_path`` set to null and
    ``pip_log_write_error`` set (stdout/stderr in the API response are unchanged).
    """
    config_path = _resolve_active_config_path()
    config_dir = config_path.parent
    log_root = resolve_server_log_dir()
    subdir = log_root / PROJECT_PIP_LOG_SUBDIR
    try:
        subdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        err = f"cannot create pip log directory {subdir}: {e}"
        logger.warning("%s", err)
        return {
            "pip_output_log_path": None,
            "pip_output_log_relative": None,
            "pip_logs_directory": str(log_root),
            "pip_log_write_error": err,
        }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = secrets.token_hex(4)
    safe_cmd = "".join(c if c.isalnum() or c in "-_" else "_" for c in command_name)[
        :64
    ]
    # Subdirectory is already ``project_pip/``; stem is the MCP command name + timestamp.
    stem = f"{safe_cmd}_{ts}_{nonce}"
    log_path = subdir / f"{stem}.log"

    header_lines = [
        "# ai-editor-server project_pip session log",
        f"# command={command_name}",
        f"# project_id={project_id}",
        f"# config_dir={config_dir}",
    ]
    if job_id:
        header_lines.append(f"# job_id={job_id}")
    header_lines.append(f"# pip_args={pip_args!r}")
    header_lines.append("")
    header_lines.append("--- stdout ---")
    header_lines.append(stdout if stdout else "")
    header_lines.append("")
    header_lines.append("--- stderr ---")
    header_lines.append(stderr if stderr else "")
    header_lines.append("")
    header_lines.append("--- process ---")
    header_lines.append(f"returncode={returncode!r}")
    header_lines.append(f"timed_out={timed_out!r}")
    header_lines.append("")

    body = "\n".join(header_lines)
    try:
        log_path.write_text(body, encoding="utf-8")
    except OSError as e:
        err = f"cannot write pip log file {log_path}: {e}"
        logger.warning("%s", err)
        return {
            "pip_output_log_path": None,
            "pip_output_log_relative": None,
            "pip_logs_directory": str(log_root),
            "pip_log_write_error": err,
        }

    try:
        rel = log_path.resolve().relative_to(config_dir.resolve())
        rel_str = rel.as_posix()
    except ValueError:
        rel_str = None

    logger.info(
        "Wrote project_pip session log: %s (command=%s project_id=%s)",
        log_path,
        command_name,
        project_id,
    )
    return {
        "pip_output_log_path": str(log_path.resolve()),
        "pip_output_log_relative": rel_str,
        "pip_logs_directory": str(log_root),
        "pip_log_write_error": None,
    }
