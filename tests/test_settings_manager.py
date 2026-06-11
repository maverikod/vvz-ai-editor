"""
Tests for SettingsManager.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import pytest
from unittest.mock import patch
from ai_editor.core.settings_manager import (
    SettingsManager,
    get_settings,
    get_setting,
)


class TestSettingsManagerSingleton:
    """Test singleton pattern."""

    def test_singleton_instance(self):
        """Test that SettingsManager is a singleton."""
        # Reset singleton for testing
        SettingsManager._instance = None
        SettingsManager._initialized = False

        instance1 = SettingsManager()
        instance2 = SettingsManager()
        instance3 = get_settings()

        assert instance1 is instance2
        assert instance1 is instance3
        assert instance2 is instance3


class TestSettingsManagerDefaults:
    """Test default values from constants."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_code_file_extensions_default(self):
        """Test default code file extensions (only .py for indexing)."""
        settings = SettingsManager()
        extensions = settings.get("code_file_extensions")
        assert isinstance(extensions, set)
        assert ".py" in extensions
        assert len(extensions) >= 1

    def test_max_file_lines_default(self):
        """Test default max file lines."""
        settings = SettingsManager()
        assert settings.get("max_file_lines") == 400

    def test_server_port_default(self):
        """Test default server port."""
        settings = SettingsManager()
        assert settings.get("server_port") == 15000

    def test_server_host_default(self):
        """Test default server host."""
        settings = SettingsManager()
        assert settings.get("server_host") == "0.0.0.0"

    def test_poll_interval_default(self):
        """Test default poll interval."""
        settings = SettingsManager()
        assert settings.get("poll_interval") == 30

    def test_scan_interval_default(self):
        """Test default scan interval."""
        settings = SettingsManager()
        assert settings.get("scan_interval") == 60

    def test_batch_size_default(self):
        """Test default batch size."""
        settings = SettingsManager()
        assert settings.get("batch_size") == 10

    def test_vector_dim_default(self):
        """Test default vector dimension."""
        settings = SettingsManager()
        assert settings.get("vector_dim") == 384

    def test_projectid_filename_default(self):
        """Test default projectid filename."""
        settings = SettingsManager()
        assert settings.get("projectid_filename") == "projectid"


class TestSettingsManagerCLIOverrides:
    """Test CLI overrides (highest priority)."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_cli_override_server_port(self):
        """Test CLI override for server port."""
        settings = SettingsManager()
        settings.set_cli_overrides({"server_port": 16000})
        assert settings.get("server_port") == 16000

    def test_cli_override_poll_interval(self):
        """Test CLI override for poll interval."""
        settings = SettingsManager()
        settings.set_cli_overrides({"poll_interval": 60})
        assert settings.get("poll_interval") == 60

    def test_cli_override_batch_size(self):
        """Test CLI override for batch size."""
        settings = SettingsManager()
        settings.set_cli_overrides({"batch_size": 20})
        assert settings.get("batch_size") == 20

    def test_cli_override_multiple_settings(self):
        """Test CLI override for multiple settings."""
        settings = SettingsManager()
        settings.set_cli_overrides(
            {
                "server_port": 16000,
                "poll_interval": 60,
                "batch_size": 20,
            }
        )
        assert settings.get("server_port") == 16000
        assert settings.get("poll_interval") == 60
        assert settings.get("batch_size") == 20

    def test_cli_override_updates_existing(self):
        """Test that CLI override updates existing overrides."""
        settings = SettingsManager()
        settings.set_cli_overrides({"server_port": 16000})
        assert settings.get("server_port") == 16000

        settings.set_cli_overrides({"server_port": 17000})
        assert settings.get("server_port") == 17000


class TestSettingsManagerEnvironmentVariables:
    """Test environment variable loading."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_env_var_server_port(self):
        """Test loading server port from environment."""
        with patch.dict(os.environ, {"AI_EDITOR_SERVER_PORT": "16000"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            assert settings.get("server_port") == 16000

    def test_env_var_poll_interval(self):
        """Test loading poll interval from environment."""
        with patch.dict(os.environ, {"AI_EDITOR_POLL_INTERVAL": "60"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            assert settings.get("poll_interval") == 60

    def test_env_var_batch_size(self):
        """Test loading batch size from environment."""
        with patch.dict(os.environ, {"AI_EDITOR_BATCH_SIZE": "20"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            assert settings.get("batch_size") == 20

    def test_env_var_code_file_extensions(self):
        """Test loading code file extensions from environment."""
        with patch.dict(
            os.environ, {"AI_EDITOR_CODE_FILE_EXTENSIONS": ".py,.js,.ts"}
        ):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            extensions = settings.get("code_file_extensions")
            assert isinstance(extensions, set)
            assert ".py" in extensions
            assert ".js" in extensions
            assert ".ts" in extensions

    def test_env_var_invalid_int(self):
        """Test handling invalid integer environment variable."""
        with patch.dict(os.environ, {"AI_EDITOR_SERVER_PORT": "invalid"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            # Should fall back to default
            assert settings.get("server_port") == 15000

    def test_env_var_invalid_float(self):
        """Test handling invalid float environment variable."""
        with patch.dict(os.environ, {"AI_EDITOR_RETRY_DELAY": "invalid"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            # Should fall back to default
            assert settings.get("retry_delay") == 10.0


class TestSettingsManagerPriority:
    """Test priority: CLI > ENV > Constants."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_priority_cli_overrides_env(self):
        """Test CLI overrides environment variable."""
        with patch.dict(os.environ, {"AI_EDITOR_SERVER_PORT": "16000"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            settings.set_cli_overrides({"server_port": 17000})
            assert settings.get("server_port") == 17000  # CLI wins

    def test_priority_env_overrides_constants(self):
        """Test environment variable overrides constants."""
        with patch.dict(os.environ, {"AI_EDITOR_SERVER_PORT": "16000"}):
            SettingsManager._instance = None
            SettingsManager._initialized = False
            settings = SettingsManager()
            assert settings.get("server_port") == 16000  # ENV wins over default

    def test_priority_constants_when_no_override(self):
        """Test constants used when no override."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        settings = SettingsManager()
        assert settings.get("server_port") == 15000  # Default from constants


class TestSettingsManagerProperties:
    """Test convenience properties."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_code_file_extensions_property(self):
        """Test code_file_extensions property."""
        settings = SettingsManager()
        extensions = settings.code_file_extensions
        assert isinstance(extensions, set)
        assert ".py" in extensions

    def test_max_file_lines_property(self):
        """Test max_file_lines property."""
        settings = SettingsManager()
        assert settings.max_file_lines == 400

    def test_poll_interval_property(self):
        """Test poll_interval property."""
        settings = SettingsManager()
        assert settings.poll_interval == 30

    def test_scan_interval_property(self):
        """Test scan_interval property."""
        settings = SettingsManager()
        assert settings.scan_interval == 60

    def test_server_host_property(self):
        """Test server_host property."""
        settings = SettingsManager()
        assert settings.server_host == "0.0.0.0"

    def test_server_port_property(self):
        """Test server_port property."""
        settings = SettingsManager()
        assert settings.server_port == 15000

    def test_vector_dim_property(self):
        """Test vector_dim property."""
        settings = SettingsManager()
        assert settings.vector_dim == 384

    def test_batch_size_property(self):
        """Test batch_size property."""
        settings = SettingsManager()
        assert settings.batch_size == 10

    def test_retry_attempts_property(self):
        """Test retry_attempts property."""
        settings = SettingsManager()
        assert settings.retry_attempts == 3

    def test_retry_delay_property(self):
        """Test retry_delay property."""
        settings = SettingsManager()
        assert settings.retry_delay == 10.0


class TestSettingsManagerGetMethod:
    """Test get() method."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_get_existing_setting(self):
        """Test getting existing setting."""
        settings = SettingsManager()
        assert settings.get("server_port") == 15000

    def test_get_nonexistent_setting_with_default(self):
        """Test getting nonexistent setting with default."""
        settings = SettingsManager()
        value = settings.get("nonexistent_setting", default="default_value")
        assert value == "default_value"

    def test_get_nonexistent_setting_without_default(self):
        """Test getting nonexistent setting without default raises KeyError."""
        settings = SettingsManager()
        with pytest.raises(KeyError):
            settings.get("nonexistent_setting")


class TestGetSettingsFunction:
    """Test get_settings() convenience function."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_get_settings_returns_instance(self):
        """Test get_settings() returns SettingsManager instance."""
        settings = get_settings()
        assert isinstance(settings, SettingsManager)

    def test_get_settings_singleton(self):
        """Test get_settings() returns same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2


class TestGetSettingFunction:
    """Test get_setting() convenience function."""

    def setup_method(self):
        """Reset singleton before each test."""
        SettingsManager._instance = None
        SettingsManager._initialized = False
        SettingsManager._cli_overrides = {}

    def test_get_setting_returns_value(self):
        """Test get_setting() returns setting value."""
        value = get_setting("server_port")
        assert value == 15000

    def test_get_setting_with_default(self):
        """Test get_setting() with default value."""
        value = get_setting("nonexistent_setting", default="default")
        assert value == "default"

    def test_get_setting_respects_overrides(self):
        """Test get_setting() respects CLI overrides."""
        settings = get_settings()
        settings.set_cli_overrides({"server_port": 16000})
        value = get_setting("server_port")
        assert value == 16000
