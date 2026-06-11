"""
Settings manager for unified configuration access.

Provides a single source of truth for all settings with priority:
1. CLI arguments (highest priority)
2. Environment variables
3. Constants (default values)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import logging
from typing import Any, Optional, Dict, Set

from .constants import (
    # File Extensions
    CODE_FILE_EXTENSIONS,
    CONFIG_FILE_EXTENSIONS,
    # Ignore Patterns
    DEFAULT_IGNORE_PATTERNS,
    GIT_IGNORE_PATTERNS,
    # File and Directory Names
    PROJECTID_FILENAME,
    GIT_DIR_NAME,
    GITIGNORE_FILENAME,
    VERSIONS_DIR_NAME,
    LOCKS_DIR_NAME,
    LOGS_DIR_NAME,
    DATA_DIR_NAME,
    # Sizes and Limits
    DEFAULT_MAX_FILE_LINES,
    DEFAULT_MIN_CHUNK_LENGTH,
    DEFAULT_LOG_MAX_BYTES,
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_VECTOR_DIM,
    FILE_MODIFICATION_TOLERANCE,
    LAST_MODIFIED_EPSILON,
    # Timeouts and Intervals
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_GIT_TIMEOUT,
    PROXY_DRIVER_POLL_INTERVAL,
    DB_CONNECTION_MAX_RETRIES,
    DB_CONNECTION_RETRY_DELAY,
    DEFAULT_MAX_SCAN_DURATION,
    # Analysis Patterns
    PLACEHOLDER_PATTERNS,
    STUB_PATTERNS,
    # Ports and Hosts
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_CHUNKER_PORT,
    DEFAULT_EMBEDDING_PORT,
    DEFAULT_LOCALHOST,
    # Circuit Breaker
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_RECOVERY_TIMEOUT,
    DEFAULT_SUCCESS_THRESHOLD,
    DEFAULT_INITIAL_BACKOFF,
    DEFAULT_MAX_BACKOFF,
    DEFAULT_BACKOFF_MULTIPLIER,
    # Batch Processor
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_EMPTY_ITERATIONS,
    DEFAULT_EMPTY_DELAY,
    # File Paths
    DEFAULT_DB_PATH,
    DEFAULT_FAISS_DIR,
    DEFAULT_VECTORIZATION_WORKER_LOG,
    DEFAULT_FILE_WATCHER_LOG,
    # Database Driver
    DEFAULT_DB_DRIVER_TYPE,
    # File Watcher
    FILE_WATCHER_IGNORE_PATTERNS,
)

logger = logging.getLogger(__name__)


class SettingsManager:
    """
    Unified settings manager with priority: CLI > ENV > Constants.

    This class provides a single source of truth for all configuration values.
    Settings can be overridden via CLI arguments or environment variables.
    """

    _instance: Optional["SettingsManager"] = None
    _cli_overrides: Dict[str, Any] = {}
    _initialized: bool = False

    def __new__(cls) -> "SettingsManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize settings manager."""
        if self._initialized:
            return

        self._cli_overrides = {}
        self._load_from_env()
        self._initialized = True
        logger.debug("SettingsManager initialized")

    def _load_from_env(self) -> None:
        """Load settings from environment variables."""
        # Environment variable prefix
        env_prefix = "AI_EDITOR_"

        # Map of setting names to environment variable names and type converters
        env_mappings: Dict[str, tuple[str, type]] = {
            # File Extensions (comma-separated strings)
            "code_file_extensions": (f"{env_prefix}CODE_FILE_EXTENSIONS", str),
            "config_file_extensions": (f"{env_prefix}CONFIG_FILE_EXTENSIONS", str),
            # Ignore Patterns (comma-separated strings)
            "default_ignore_patterns": (f"{env_prefix}DEFAULT_IGNORE_PATTERNS", str),
            # File and Directory Names
            "projectid_filename": (f"{env_prefix}PROJECTID_FILENAME", str),
            "git_dir_name": (f"{env_prefix}GIT_DIR_NAME", str),
            "gitignore_filename": (f"{env_prefix}GITIGNORE_FILENAME", str),
            "versions_dir_name": (f"{env_prefix}VERSIONS_DIR_NAME", str),
            "locks_dir_name": (f"{env_prefix}LOCKS_DIR_NAME", str),
            "logs_dir_name": (f"{env_prefix}LOGS_DIR_NAME", str),
            "data_dir_name": (f"{env_prefix}DATA_DIR_NAME", str),
            # Sizes and Limits
            "max_file_lines": (f"{env_prefix}MAX_FILE_LINES", int),
            "min_chunk_length": (f"{env_prefix}MIN_CHUNK_LENGTH", int),
            "log_max_bytes": (f"{env_prefix}LOG_MAX_BYTES", int),
            "log_backup_count": (f"{env_prefix}LOG_BACKUP_COUNT", int),
            "vector_dim": (f"{env_prefix}VECTOR_DIM", int),
            "file_modification_tolerance": (
                f"{env_prefix}FILE_MODIFICATION_TOLERANCE",
                float,
            ),
            "last_modified_epsilon": (f"{env_prefix}LAST_MODIFIED_EPSILON", float),
            # Timeouts and Intervals
            "poll_interval": (f"{env_prefix}POLL_INTERVAL", int),
            "scan_interval": (f"{env_prefix}SCAN_INTERVAL", int),
            "retry_attempts": (f"{env_prefix}RETRY_ATTEMPTS", int),
            "retry_delay": (f"{env_prefix}RETRY_DELAY", float),
            "command_timeout": (f"{env_prefix}COMMAND_TIMEOUT", float),
            "git_timeout": (f"{env_prefix}GIT_TIMEOUT", float),
            "proxy_driver_poll_interval": (
                f"{env_prefix}PROXY_DRIVER_POLL_INTERVAL",
                float,
            ),
            "db_connection_max_retries": (
                f"{env_prefix}DB_CONNECTION_MAX_RETRIES",
                int,
            ),
            "db_connection_retry_delay": (
                f"{env_prefix}DB_CONNECTION_RETRY_DELAY",
                float,
            ),
            "max_scan_duration": (f"{env_prefix}MAX_SCAN_DURATION", int),
            # Ports and Hosts
            "server_host": (f"{env_prefix}SERVER_HOST", str),
            "server_port": (f"{env_prefix}SERVER_PORT", int),
            "chunker_port": (f"{env_prefix}CHUNKER_PORT", int),
            "embedding_port": (f"{env_prefix}EMBEDDING_PORT", int),
            "localhost": (f"{env_prefix}LOCALHOST", str),
            # Circuit Breaker
            "failure_threshold": (f"{env_prefix}FAILURE_THRESHOLD", int),
            "recovery_timeout": (f"{env_prefix}RECOVERY_TIMEOUT", float),
            "success_threshold": (f"{env_prefix}SUCCESS_THRESHOLD", int),
            "initial_backoff": (f"{env_prefix}INITIAL_BACKOFF", float),
            "max_backoff": (f"{env_prefix}MAX_BACKOFF", float),
            "backoff_multiplier": (f"{env_prefix}BACKOFF_MULTIPLIER", float),
            # Batch Processor
            "batch_size": (f"{env_prefix}BATCH_SIZE", int),
            "max_empty_iterations": (f"{env_prefix}MAX_EMPTY_ITERATIONS", int),
            "empty_delay": (f"{env_prefix}EMPTY_DELAY", float),
            # File Paths
            "db_path": (f"{env_prefix}DB_PATH", str),
            "faiss_dir": (f"{env_prefix}FAISS_DIR", str),
            "vectorization_worker_log": (f"{env_prefix}VECTORIZATION_WORKER_LOG", str),
            "file_watcher_log": (f"{env_prefix}FILE_WATCHER_LOG", str),
            # Database Driver
            "db_driver_type": (f"{env_prefix}DB_DRIVER_TYPE", str),
        }

        for setting_name, (env_var, converter) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    value: Any
                    if converter == str:
                        # For string lists (comma-separated), split them
                        if setting_name in (
                            "code_file_extensions",
                            "config_file_extensions",
                            "default_ignore_patterns",
                        ):
                            value = set(
                                v.strip() for v in env_value.split(",") if v.strip()
                            )
                        else:
                            value = env_value
                    elif converter == int:
                        value = int(env_value)
                    elif converter == float:
                        value = float(env_value)
                    else:
                        value = env_value
                    self._cli_overrides[setting_name] = value
                    logger.debug(f"Loaded {setting_name} from environment: {value}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse {env_var}={env_value}: {e}")

    def set_cli_overrides(self, overrides: Dict[str, Any]) -> None:
        """
        Set CLI argument overrides (highest priority).

        Args:
            overrides: Dictionary of setting names to values
        """
        self._cli_overrides.update(overrides)
        logger.debug(f"CLI overrides set: {list(overrides.keys())}")

    def get(self, setting_name: str, default: Any = None) -> Any:
        """
        Get setting value with priority: CLI > ENV > Constants.

        Args:
            setting_name: Name of the setting
            default: Default value if not found (optional)

        Returns:
            Setting value
        """
        # Check CLI overrides first (highest priority)
        if setting_name in self._cli_overrides:
            return self._cli_overrides[setting_name]

        # Check constants (lowest priority, used as defaults)
        constants_map = {
            # File Extensions
            "code_file_extensions": CODE_FILE_EXTENSIONS,
            "config_file_extensions": CONFIG_FILE_EXTENSIONS,
            # Ignore Patterns
            "default_ignore_patterns": DEFAULT_IGNORE_PATTERNS,
            "git_ignore_patterns": GIT_IGNORE_PATTERNS,
            # File and Directory Names
            "projectid_filename": PROJECTID_FILENAME,
            "git_dir_name": GIT_DIR_NAME,
            "gitignore_filename": GITIGNORE_FILENAME,
            "versions_dir_name": VERSIONS_DIR_NAME,
            "locks_dir_name": LOCKS_DIR_NAME,
            "logs_dir_name": LOGS_DIR_NAME,
            "data_dir_name": DATA_DIR_NAME,
            # Sizes and Limits
            "max_file_lines": DEFAULT_MAX_FILE_LINES,
            "min_chunk_length": DEFAULT_MIN_CHUNK_LENGTH,
            "log_max_bytes": DEFAULT_LOG_MAX_BYTES,
            "log_backup_count": DEFAULT_LOG_BACKUP_COUNT,
            "vector_dim": DEFAULT_VECTOR_DIM,
            "file_modification_tolerance": FILE_MODIFICATION_TOLERANCE,
            "last_modified_epsilon": LAST_MODIFIED_EPSILON,
            # Timeouts and Intervals
            "poll_interval": DEFAULT_POLL_INTERVAL,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
            "retry_attempts": DEFAULT_RETRY_ATTEMPTS,
            "retry_delay": DEFAULT_RETRY_DELAY,
            "command_timeout": DEFAULT_COMMAND_TIMEOUT,
            "git_timeout": DEFAULT_GIT_TIMEOUT,
            "proxy_driver_poll_interval": PROXY_DRIVER_POLL_INTERVAL,
            "db_connection_max_retries": DB_CONNECTION_MAX_RETRIES,
            "db_connection_retry_delay": DB_CONNECTION_RETRY_DELAY,
            "max_scan_duration": DEFAULT_MAX_SCAN_DURATION,
            # Analysis Patterns
            "placeholder_patterns": PLACEHOLDER_PATTERNS,
            "stub_patterns": STUB_PATTERNS,
            # Ports and Hosts
            "server_host": DEFAULT_SERVER_HOST,
            "server_port": DEFAULT_SERVER_PORT,
            "chunker_port": DEFAULT_CHUNKER_PORT,
            "embedding_port": DEFAULT_EMBEDDING_PORT,
            "localhost": DEFAULT_LOCALHOST,
            # Circuit Breaker
            "failure_threshold": DEFAULT_FAILURE_THRESHOLD,
            "recovery_timeout": DEFAULT_RECOVERY_TIMEOUT,
            "success_threshold": DEFAULT_SUCCESS_THRESHOLD,
            "initial_backoff": DEFAULT_INITIAL_BACKOFF,
            "max_backoff": DEFAULT_MAX_BACKOFF,
            "backoff_multiplier": DEFAULT_BACKOFF_MULTIPLIER,
            # Batch Processor
            "batch_size": DEFAULT_BATCH_SIZE,
            "max_empty_iterations": DEFAULT_MAX_EMPTY_ITERATIONS,
            "empty_delay": DEFAULT_EMPTY_DELAY,
            # File Paths
            "db_path": DEFAULT_DB_PATH,
            "faiss_dir": DEFAULT_FAISS_DIR,
            "vectorization_worker_log": DEFAULT_VECTORIZATION_WORKER_LOG,
            "file_watcher_log": DEFAULT_FILE_WATCHER_LOG,
            # Database Driver
            "db_driver_type": DEFAULT_DB_DRIVER_TYPE,
            # File Watcher
            "file_watcher_ignore_patterns": FILE_WATCHER_IGNORE_PATTERNS,
        }

        if setting_name in constants_map:
            return constants_map[setting_name]

        if default is not None:
            return default

        raise KeyError(f"Setting '{setting_name}' not found and no default provided")

    # Convenience properties for common settings
    @property
    def code_file_extensions(self) -> Set[str]:
        """Get code file extensions."""
        return self.get("code_file_extensions")

    @property
    def default_ignore_patterns(self) -> Set[str]:
        """Get default ignore patterns."""
        return self.get("default_ignore_patterns")

    @property
    def projectid_filename(self) -> str:
        """Get projectid filename."""
        return self.get("projectid_filename")

    @property
    def max_file_lines(self) -> int:
        """Get maximum file lines."""
        return self.get("max_file_lines")

    @property
    def min_chunk_length(self) -> int:
        """Get minimum chunk length."""
        return self.get("min_chunk_length")

    @property
    def poll_interval(self) -> int:
        """Get poll interval."""
        return self.get("poll_interval")

    @property
    def scan_interval(self) -> int:
        """Get scan interval."""
        return self.get("scan_interval")

    @property
    def server_host(self) -> str:
        """Get server host."""
        return self.get("server_host")

    @property
    def server_port(self) -> int:
        """Get server port."""
        return self.get("server_port")

    @property
    def vector_dim(self) -> int:
        """Get vector dimension."""
        return self.get("vector_dim")

    @property
    def batch_size(self) -> int:
        """Get batch size."""
        return self.get("batch_size")

    @property
    def retry_attempts(self) -> int:
        """Get retry attempts."""
        return self.get("retry_attempts")

    @property
    def retry_delay(self) -> float:
        """Get retry delay."""
        return self.get("retry_delay")


def get_settings() -> SettingsManager:
    """
    Get the global settings manager instance.

    Returns:
        SettingsManager instance
    """
    return SettingsManager()


# Convenience function for quick access
def get_setting(setting_name: str, default: Any = None) -> Any:
    """
    Get a setting value quickly.

    Args:
        setting_name: Name of the setting
        default: Default value if not found

    Returns:
        Setting value
    """
    return get_settings().get(setting_name, default)
