"""
Configuration management for MCP server.

Provides configuration schema, validation, and generation.
Re-exports ProjectDir, SVOServiceConfig, ServerConfig from config_models.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from .config_models import ProjectDir, SVOServiceConfig
from .config_server import ServerConfig
from .constants import (
    DEFAULT_CHUNKER_PORT,
    DEFAULT_EMBEDDING_PORT,
    DEFAULT_LOCALHOST,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
)


def generate_config(
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    log: Optional[str] = None,
    db_path: Optional[str] = None,
    dirs: Optional[List[Dict[str, str]]] = None,
    chunker_host: str = DEFAULT_LOCALHOST,
    chunker_port: int = DEFAULT_CHUNKER_PORT,
    embedding_host: str = DEFAULT_LOCALHOST,
    embedding_port: int = DEFAULT_EMBEDDING_PORT,
    mtls_certificates: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generate server configuration.

    Args:
        host: Server host (default from constants)
        port: Server port (default from constants)
        log: Path to log file (optional)
        db_path: Path to SQLite database (optional)
        dirs: List of directories with 'name' and 'path' keys.
              UUID4 will be generated automatically.
        chunker_host, chunker_port, embedding_host, embedding_port: SVO service params.
        mtls_certificates: Optional dict with cert_file, key_file, ca_cert_file, crl_file.

    Returns:
        Configuration dictionary
    """
    config_dirs = []
    if dirs:
        for dir_info in dirs:
            name = dir_info.get("name", Path(dir_info["path"]).name)
            path = Path(dir_info["path"]).resolve()
            if not path.exists():
                raise ValueError(f"Path does not exist: {path}")
            if not path.is_dir():
                raise ValueError(f"Path is not a directory: {path}")

            config_dirs.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "path": str(path),
                }
            )

    config: Dict[str, Any] = {
        "host": host,
        "port": port,
        "dirs": config_dirs,
        "file_lock": {
            "timeout_seconds": 30.0,
            "poll_interval_seconds": 0.05,
            "default_read_mode": "full",
        },
        "sessions": {
            "show_session_ids": False,
        },
        "security": {
            "policy": "disabled",
        },
    }
    if log:
        log_path = Path(log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        config["log"] = str(log_path.resolve())
    if db_path:
        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        config["db_path"] = str(db_path_obj.resolve())

    cert_file = None
    key_file = None
    ca_cert_file = None
    crl_file = None
    if mtls_certificates:
        cert_file = mtls_certificates.get("cert_file") or mtls_certificates.get("cert")
        key_file = mtls_certificates.get("key_file") or mtls_certificates.get("key")
        ca_cert_file = mtls_certificates.get("ca_cert_file") or mtls_certificates.get(
            "ca_cert"
        )
        crl_file = mtls_certificates.get("crl_file") or mtls_certificates.get("crl")

    protocol = "mtls" if (cert_file and key_file) else "https"

    config["chunker"] = {
        "enabled": True,
        "host": chunker_host,
        "port": chunker_port,
        "protocol": protocol,
        "cert_file": cert_file,
        "key_file": key_file,
        "ca_cert_file": ca_cert_file,
        "crl_file": crl_file,
    }
    config["embedding"] = {
        "enabled": True,
        "host": embedding_host,
        "port": embedding_port,
        "protocol": protocol,
        "cert_file": cert_file,
        "key_file": key_file,
        "ca_cert_file": ca_cert_file,
        "crl_file": crl_file,
    }

    return config


def validate_config(
    config_path: Path,
) -> tuple[bool, Optional[str], Optional[ServerConfig]]:
    """
    Validate configuration file.

    Args:
        config_path: Path to configuration file

    Returns:
        Tuple of (is_valid, error_message, config_object)
    """
    try:
        if not config_path.exists():
            return False, f"Configuration file not found: {config_path}", None

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        config = ServerConfig(**config_data)

        ids = [d.id for d in config.dirs]
        names = [d.name for d in config.dirs]

        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            return (
                False,
                f"Duplicate project IDs found: {set(duplicates)}",
                None,
            )

        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            return (
                False,
                f"Duplicate project names found: {set(duplicates)}",
                None,
            )

        return True, None, config

    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}", None
    except ValueError as e:
        return False, f"Validation error: {str(e)}", None
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", None


def load_config(config_path: Path) -> ServerConfig:
    """
    Load and validate configuration.

    Args:
        config_path: Path to configuration file

    Returns:
        ServerConfig object

    Raises:
        ValueError: If configuration is invalid
    """
    is_valid, error, config = validate_config(config_path)
    if not is_valid:
        raise ValueError(error or "Invalid configuration")
    if config is None:
        raise ValueError("Failed to load configuration")
    return config


def save_config(config: Dict[str, Any], config_path: Path) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary
        config_path: Path to save configuration
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_driver_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract database driver configuration from full config.

    Looks for driver config in ai_editor.database.driver section.
    If not found, falls back to creating config from ai_editor.db_path.

    Args:
        config: Full configuration dictionary

    Returns:
        Driver configuration dict with 'type' and 'config' keys, or None if not found
    """
    ai_editor = config.get("ai_editor", {})
    if not ai_editor:
        return None

    database = ai_editor.get("database", {})
    if database and isinstance(database, dict):
        driver = database.get("driver")
        if driver and isinstance(driver, dict):
            driver_type = driver.get("type")
            driver_config = driver.get("config", {})
            if driver_type and driver_config:
                merged_cfg: Dict[str, Any] = dict(driver_config)
                if str(driver_type).strip().lower() == "postgres":
                    vd = ai_editor.get("vector_dim")
                    if vd is not None:
                        merged_cfg["vector_dim"] = int(vd)
                    vsb = ai_editor.get("vector_search_backend")
                    if vsb is not None:
                        merged_cfg["vector_search_backend"] = vsb
                return {
                    "type": driver_type,
                    "config": merged_cfg,
                }

    db_path = ai_editor.get("db_path")
    if db_path:
        from .database.base import create_driver_config_for_worker

        return cast(
            Dict[str, Any],
            create_driver_config_for_worker(Path(db_path), driver_type="sqlite_proxy"),
        )

    return None
