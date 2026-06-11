"""
Server management utilities for testing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from scripts.pipeline.config import PipelineConfig


class ServerManager:
    """Manages test server process."""

    def __init__(self, config: "PipelineConfig"):  # noqa: F821
        """Initialize server manager.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.config_file: Optional[Path] = None
        self._repo_root = Path(__file__).parent.parent.parent

    def _apply_schema(self, timeout: int = 120) -> bool:
        """Apply DB schema from config before server start."""
        if self.config_file is None:
            return False
        python = sys.executable
        args = [
            python,
            "-m",
            "ai_editor.cli.config_cli",
            "schema",
            "--file",
            str(self.config_file),
        ]
        try:
            result = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run_server_cli(self, command: str, timeout: int = 30) -> bool:
        """Run server manager CLI command for the current test config."""
        if self.config_file is None:
            return False
        args = [
            sys.executable,
            "-m",
            "ai_editor.cli.server_manager_cli",
            "--config",
            str(self.config_file),
            command,
        ]
        try:
            result = subprocess.run(
                args,
                cwd=self._repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_server(self, timeout: int = 30) -> bool:
        """Start test server.

        Args:
            timeout: Timeout in seconds to wait for server to start

        Returns:
            True if server started successfully
        """
        # Keep deterministic config path so stop/start always target same daemon.
        self.config_file = self._repo_root / "test_config_pipeline.json"
        self.config.create_test_config(self.config_file)
        if not self._apply_schema():
            return False

        # Best-effort cleanup of stale daemon from previous runs.
        self._run_server_cli("stop", timeout=timeout)
        if not self._run_server_cli("start", timeout=timeout):
            return False
        # Wait for server listener.
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._can_connect():
                return True
            time.sleep(0.5)
        return False

    def stop_server(self, timeout: int = 10) -> bool:
        """Stop test server.

        Args:
            timeout: Timeout in seconds to wait for server to stop

        Returns:
            True if server stopped successfully
        """
        if self.config_file is None:
            self.config_file = self._repo_root / "test_config_pipeline.json"
        if not self._run_server_cli("stop", timeout=timeout):
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._can_connect():
                break
            time.sleep(0.2)
        if self.config_file.exists():
            try:
                self.config_file.unlink()
            except Exception:
                pass
        self.config_file = None
        return True

    def is_server_running(self) -> bool:
        """Check if server is running.

        Returns:
            True if server is running
        """
        return self._can_connect()

    def _can_connect(self) -> bool:
        """Return True when configured host/port accepts TCP connections."""
        network = self.config.get_network_settings()
        host = str(network.get("host", "127.0.0.1"))
        port = int(network.get("port", 15001))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except Exception:
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def restart_server(self, timeout: int = 30) -> bool:
        """Restart test server.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if server restarted successfully
        """
        if not self.stop_server(timeout=timeout):
            return False

        time.sleep(1)  # Brief pause between stop and start

        return self.start_server(timeout=timeout)
