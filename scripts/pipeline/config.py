"""
Test pipeline configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


class PipelineConfig:
    """Configuration for test pipeline."""

    def __init__(
        self,
        test_data_dir: Optional[Path] = None,
        test_db_path: Optional[Path] = None,
        server_config_path: Optional[Path] = None,
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        timeout: int = 900,
    ):
        """Initialize pipeline configuration.

        Args:
            test_data_dir: Path to test_data directory
            test_db_path: Path to test database file
            server_config_path: Path to server config file
            server_host: Server host for testing
            server_port: Server port for testing
            timeout: Test timeout in seconds (default 900)
        """
        self.test_data_dir = (
            test_data_dir or Path(__file__).parent.parent.parent / "test_data"
        )
        self.test_db_path = test_db_path
        self.server_config_path = server_config_path
        self.server_host = server_host
        self.server_port = server_port
        self.timeout = timeout

    def get_db_path(self) -> Path:
        """Return absolute database path used by real server config."""
        if self.test_db_path is not None:
            return self.test_db_path.expanduser().resolve()

        config = self._load_base_config()
        ai_editor_section = config.get("ai_editor", {})
        if isinstance(ai_editor_section, dict):
            db_path = ai_editor_section.get("db_path")
            if isinstance(db_path, str) and db_path.strip():
                db_candidate = Path(db_path).expanduser()
                if db_candidate.is_absolute():
                    return db_candidate.resolve()
                repo_root = Path(__file__).parent.parent.parent
                return (repo_root / db_candidate).resolve()

        return (Path(tempfile.gettempdir()) / "test_ai_editor.db").resolve()

    def get_test_projects(self) -> list[Path]:
        """Get list of test project directories.

        Returns:
            List of project paths
        """
        projects: list[Path] = []
        if not self.test_data_dir.exists():
            return projects

        for item in self.test_data_dir.iterdir():
            if item.is_dir() and (item / "projectid").exists():
                projects.append(item)

        return projects

    def _load_base_config(self) -> Dict[str, Any]:
        """Load base server config from repository root config.json."""
        base_config_path = (
            self.server_config_path
            if self.server_config_path is not None
            else Path(__file__).parent.parent.parent / "config.json"
        )
        if not base_config_path.exists():
            return {}

        with open(base_config_path, "r", encoding="utf-8") as f:
            loaded_config: Any = json.load(f)

        if isinstance(loaded_config, dict):
            return loaded_config
        return {}

    @staticmethod
    def _extract_network_settings(config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract host/port/protocol from config with deterministic defaults."""
        server_section = config.get("server", {})
        if not isinstance(server_section, dict):
            server_section = {}

        return {
            "host": server_section.get("host", "127.0.0.1"),
            "port": server_section.get("port", 15001),
            "protocol": server_section.get("protocol", "http"),
        }

    @staticmethod
    def _extract_ssl_paths_from_section(ssl_section: Any) -> Dict[str, str]:
        """Normalize cert/key/ca paths from an ssl dict."""
        if not isinstance(ssl_section, dict):
            return {}
        mtls_paths: Dict[str, str] = {}
        for key in ("cert", "key", "ca", "cert_path", "key_path", "ca_path"):
            value = ssl_section.get(key)
            if value:
                mtls_paths[key] = str(Path(str(value)).expanduser().resolve())
        return mtls_paths

    @staticmethod
    def _extract_mtls_ssl_paths(config: Dict[str, Any]) -> Dict[str, str]:
        """Extract normalized mTLS certificate paths from server config (server.ssl)."""
        server_section = config.get("server", {})
        if not isinstance(server_section, dict):
            server_section = {}
        ssl_section = server_section.get("ssl", {})
        if not isinstance(ssl_section, dict):
            ssl_section = config.get("ssl", {})
        return PipelineConfig._extract_ssl_paths_from_section(ssl_section)

    @staticmethod
    def _extract_client_mtls_ssl_paths(config: Dict[str, Any]) -> Dict[str, str]:
        """Extract client cert/key/ca for outgoing mTLS (client.ssl). Fallback to server.ssl."""
        client_section = config.get("client", {})
        if isinstance(client_section, dict):
            ssl_section = client_section.get("ssl", {})
            if isinstance(ssl_section, dict) and any(
                ssl_section.get(k) for k in ("cert", "cert_path", "key", "key_path")
            ):
                return PipelineConfig._extract_ssl_paths_from_section(ssl_section)
        return PipelineConfig._extract_mtls_ssl_paths(config)

    def build_test_config(self) -> Dict[str, Any]:
        """Build test config where DB and network values are single-source-of-truth."""
        config = self._load_base_config()

        if "server" not in config or not isinstance(config["server"], dict):
            config["server"] = {}
        if self.server_host is not None:
            config["server"]["host"] = self.server_host
        if self.server_port is not None:
            config["server"]["port"] = self.server_port

        if "ai_editor" not in config or not isinstance(
            config["ai_editor"], dict
        ):
            config["ai_editor"] = {}
        config["ai_editor"]["db_path"] = str(self.get_db_path())

        worker_section = config["ai_editor"].setdefault("worker", {})
        if not isinstance(worker_section, dict):
            worker_section = {}
            config["ai_editor"]["worker"] = worker_section
        # Pipeline tests need deterministic DB writes from direct command calls.
        # Disable background workers to avoid concurrent writes and DB lock contention.
        worker_section["enabled"] = False

        indexing_worker = config["ai_editor"].setdefault("indexing_worker", {})
        if not isinstance(indexing_worker, dict):
            indexing_worker = {}
            config["ai_editor"]["indexing_worker"] = indexing_worker
        indexing_worker["enabled"] = False

        file_watcher = config["ai_editor"].setdefault("file_watcher", {})
        if not isinstance(file_watcher, dict):
            file_watcher = {}
            config["ai_editor"]["file_watcher"] = file_watcher
        file_watcher["enabled"] = False

        watch_dirs = worker_section.setdefault("watch_dirs", [])
        if not isinstance(watch_dirs, list):
            watch_dirs = []
            worker_section["watch_dirs"] = watch_dirs

        test_data_path = str(self.test_data_dir.absolute())
        found = False
        for watch_dir in watch_dirs:
            if isinstance(watch_dir, dict) and watch_dir.get("path") == test_data_path:
                found = True
                break
            if isinstance(watch_dir, str) and watch_dir == test_data_path:
                found = True
                break

        if not found:
            watch_dirs.append({"id": "test-pipeline", "path": test_data_path})

        return config

    def create_test_config(self, output_path: Path) -> None:
        """Create test server configuration file from unified config source."""
        config = self.build_test_config()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def get_db_path_from_config(self, config_path: Path) -> Path:
        """Load absolute DB path from an already written config file."""
        with open(config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)

        ai_editor_section = config.get("ai_editor", {})
        if not isinstance(ai_editor_section, dict):
            raise ValueError("Invalid config format: ai_editor must be an object")

        db_path = ai_editor_section.get("db_path")
        if not db_path:
            raise ValueError("Invalid config format: ai_editor.db_path is missing")

        return Path(str(db_path)).expanduser().resolve()

    def get_network_settings(self) -> Dict[str, Any]:
        """Return host/port/protocol from generated server config."""
        return self._extract_network_settings(self.build_test_config())

    def get_mtls_ssl_paths(self) -> Dict[str, str]:
        """Return normalized SSL path mapping for client connection when protocol=mtls (client.ssl)."""
        config = self.build_test_config()
        network = self._extract_network_settings(config)
        if str(network.get("protocol", "")).lower() != "mtls":
            return {}
        ssl_paths = self._extract_client_mtls_ssl_paths(config)
        required_paths = ("cert", "key", "ca")
        missing = [name for name in required_paths if not ssl_paths.get(name)]
        if missing:
            raise ValueError(
                "mTLS protocol requires client SSL paths for "
                f"{', '.join(missing)} in client.ssl (or server.ssl fallback)"
            )
        return ssl_paths

    def generate_adapter_client_settings(self) -> Dict[str, Any]:
        """Generate adapter/client settings directly from server config values."""
        config = self.build_test_config()
        settings = self._extract_network_settings(config)
        if str(settings["protocol"]).lower() == "mtls":
            settings["ssl"] = self.get_mtls_ssl_paths()
        return settings

    def validate_adapter_settings(
        self,
        adapter_settings: Dict[str, Any],
        server_config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Validate adapter settings are fully aligned with server config values."""
        reference_config = server_config or self.build_test_config()
        expected_network = self._extract_network_settings(reference_config)

        for key in ("host", "port", "protocol"):
            if adapter_settings.get(key) != expected_network.get(key):
                raise ValueError(
                    f"Adapter/server mismatch for '{key}': "
                    f"{adapter_settings.get(key)!r} != {expected_network.get(key)!r}"
                )

        protocol = str(expected_network.get("protocol", "")).lower()
        if protocol == "mtls":
            # Adapter is the outgoing client: expect client.ssl (fallback server.ssl)
            expected_ssl = self._extract_client_mtls_ssl_paths(reference_config)
            required_ssl = ("cert", "key", "ca")
            missing_in_config = [
                name for name in required_ssl if not expected_ssl.get(name)
            ]
            if missing_in_config:
                raise ValueError(
                    "Server config protocol is mtls but client.ssl (or server.ssl) is missing "
                    f"{', '.join(missing_in_config)}"
                )
            adapter_ssl = adapter_settings.get("ssl")
            if not isinstance(adapter_ssl, dict):
                raise ValueError("Adapter SSL settings are required for mtls protocol")
            for key, expected_value in expected_ssl.items():
                adapter_value = adapter_ssl.get(key)
                if adapter_value is None:
                    raise ValueError(f"Missing adapter SSL path for '{key}'")
                normalized_adapter = str(
                    Path(str(adapter_value)).expanduser().resolve()
                )
                if normalized_adapter != expected_value:
                    raise ValueError(
                        f"Adapter/client SSL mismatch for '{key}': "
                        f"{normalized_adapter!r} != {expected_value!r}"
                    )

        return True

    def verify_test_data(self) -> bool:
        """Verify test data is available.

        Returns:
            True if test data is available
        """
        if not self.test_data_dir.exists():
            return False

        projects = self.get_test_projects()
        return len(projects) > 0
