"""
Tests for project constants.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from ai_editor.core import constants


class TestConstants:
    """Test that all constants are defined and have correct types."""

    def test_code_file_extensions_defined(self):
        """Test CODE_FILE_EXTENSIONS is defined."""
        assert hasattr(constants, "CODE_FILE_EXTENSIONS")
        assert isinstance(constants.CODE_FILE_EXTENSIONS, set)
        assert len(constants.CODE_FILE_EXTENSIONS) > 0
        assert ".py" in constants.CODE_FILE_EXTENSIONS

    def test_config_file_extensions_defined(self):
        """Test CONFIG_FILE_EXTENSIONS is defined."""
        assert hasattr(constants, "CONFIG_FILE_EXTENSIONS")
        assert isinstance(constants.CONFIG_FILE_EXTENSIONS, set)
        assert len(constants.CONFIG_FILE_EXTENSIONS) > 0

    def test_default_ignore_patterns_defined(self):
        """Test DEFAULT_IGNORE_PATTERNS is defined."""
        assert hasattr(constants, "DEFAULT_IGNORE_PATTERNS")
        assert isinstance(constants.DEFAULT_IGNORE_PATTERNS, set)
        assert "__pycache__" in constants.DEFAULT_IGNORE_PATTERNS
        assert ".git" in constants.DEFAULT_IGNORE_PATTERNS

    def test_git_ignore_patterns_defined(self):
        """Test GIT_IGNORE_PATTERNS is defined."""
        assert hasattr(constants, "GIT_IGNORE_PATTERNS")
        assert isinstance(constants.GIT_IGNORE_PATTERNS, set)
        assert len(constants.GIT_IGNORE_PATTERNS) > 0

    def test_projectid_filename_defined(self):
        """Test PROJECTID_FILENAME is defined."""
        assert hasattr(constants, "PROJECTID_FILENAME")
        assert isinstance(constants.PROJECTID_FILENAME, str)
        assert constants.PROJECTID_FILENAME == "projectid"

    def test_git_dir_name_defined(self):
        """Test GIT_DIR_NAME is defined."""
        assert hasattr(constants, "GIT_DIR_NAME")
        assert isinstance(constants.GIT_DIR_NAME, str)
        assert constants.GIT_DIR_NAME == ".git"

    def test_versions_dir_name_defined(self):
        """Test VERSIONS_DIR_NAME is defined."""
        assert hasattr(constants, "VERSIONS_DIR_NAME")
        assert isinstance(constants.VERSIONS_DIR_NAME, str)

    def test_logs_dir_name_defined(self):
        """Test LOGS_DIR_NAME is defined."""
        assert hasattr(constants, "LOGS_DIR_NAME")
        assert isinstance(constants.LOGS_DIR_NAME, str)
        assert constants.LOGS_DIR_NAME == "logs"

    def test_data_dir_name_defined(self):
        """Test DATA_DIR_NAME is defined."""
        assert hasattr(constants, "DATA_DIR_NAME")
        assert isinstance(constants.DATA_DIR_NAME, str)
        assert constants.DATA_DIR_NAME == "data"

    def test_max_file_lines_defined(self):
        """Test DEFAULT_MAX_FILE_LINES is defined."""
        assert hasattr(constants, "DEFAULT_MAX_FILE_LINES")
        assert isinstance(constants.DEFAULT_MAX_FILE_LINES, int)
        assert constants.DEFAULT_MAX_FILE_LINES == 400

    def test_min_chunk_length_defined(self):
        """Test DEFAULT_MIN_CHUNK_LENGTH is defined."""
        assert hasattr(constants, "DEFAULT_MIN_CHUNK_LENGTH")
        assert isinstance(constants.DEFAULT_MIN_CHUNK_LENGTH, int)
        assert constants.DEFAULT_MIN_CHUNK_LENGTH == 30

    def test_log_max_bytes_defined(self):
        """Test DEFAULT_LOG_MAX_BYTES is defined."""
        assert hasattr(constants, "DEFAULT_LOG_MAX_BYTES")
        assert isinstance(constants.DEFAULT_LOG_MAX_BYTES, int)
        assert constants.DEFAULT_LOG_MAX_BYTES == 10485760  # 10 MB

    def test_vector_dim_defined(self):
        """Test DEFAULT_VECTOR_DIM is defined."""
        assert hasattr(constants, "DEFAULT_VECTOR_DIM")
        assert isinstance(constants.DEFAULT_VECTOR_DIM, int)
        assert constants.DEFAULT_VECTOR_DIM == 384

    def test_poll_interval_defined(self):
        """Test DEFAULT_POLL_INTERVAL is defined."""
        assert hasattr(constants, "DEFAULT_POLL_INTERVAL")
        assert isinstance(constants.DEFAULT_POLL_INTERVAL, int)
        assert constants.DEFAULT_POLL_INTERVAL == 30

    def test_scan_interval_defined(self):
        """Test DEFAULT_SCAN_INTERVAL is defined."""
        assert hasattr(constants, "DEFAULT_SCAN_INTERVAL")
        assert isinstance(constants.DEFAULT_SCAN_INTERVAL, int)
        assert constants.DEFAULT_SCAN_INTERVAL == 60

    def test_retry_attempts_defined(self):
        """Test DEFAULT_RETRY_ATTEMPTS is defined."""
        assert hasattr(constants, "DEFAULT_RETRY_ATTEMPTS")
        assert isinstance(constants.DEFAULT_RETRY_ATTEMPTS, int)
        assert constants.DEFAULT_RETRY_ATTEMPTS == 3

    def test_retry_delay_defined(self):
        """Test DEFAULT_RETRY_DELAY is defined."""
        assert hasattr(constants, "DEFAULT_RETRY_DELAY")
        assert isinstance(constants.DEFAULT_RETRY_DELAY, float)
        assert constants.DEFAULT_RETRY_DELAY == 10.0

    def test_server_port_defined(self):
        """Test DEFAULT_SERVER_PORT is defined."""
        assert hasattr(constants, "DEFAULT_SERVER_PORT")
        assert isinstance(constants.DEFAULT_SERVER_PORT, int)
        assert constants.DEFAULT_SERVER_PORT == 15000

    def test_server_host_defined(self):
        """Test DEFAULT_SERVER_HOST is defined."""
        assert hasattr(constants, "DEFAULT_SERVER_HOST")
        assert isinstance(constants.DEFAULT_SERVER_HOST, str)
        assert constants.DEFAULT_SERVER_HOST == "0.0.0.0"

    def test_placeholder_patterns_defined(self):
        """Test PLACEHOLDER_PATTERNS is defined."""
        assert hasattr(constants, "PLACEHOLDER_PATTERNS")
        assert isinstance(constants.PLACEHOLDER_PATTERNS, list)
        assert "TODO" in constants.PLACEHOLDER_PATTERNS
        assert "FIXME" in constants.PLACEHOLDER_PATTERNS

    def test_stub_patterns_defined(self):
        """Test STUB_PATTERNS is defined."""
        assert hasattr(constants, "STUB_PATTERNS")
        assert isinstance(constants.STUB_PATTERNS, list)
        assert "pass" in constants.STUB_PATTERNS

    def test_batch_size_defined(self):
        """Test DEFAULT_BATCH_SIZE is defined."""
        assert hasattr(constants, "DEFAULT_BATCH_SIZE")
        assert isinstance(constants.DEFAULT_BATCH_SIZE, int)
        assert constants.DEFAULT_BATCH_SIZE == 10

    def test_db_path_defined(self):
        """Test DEFAULT_DB_PATH is defined."""
        assert hasattr(constants, "DEFAULT_DB_PATH")
        assert isinstance(constants.DEFAULT_DB_PATH, str)
        assert constants.DEFAULT_DB_PATH == "data/ai_editor.db"

    def test_constants_immutable(self):
        """Test that constants have correct initial values."""
        # Note: In Python, we can't truly make constants immutable without using
        # __setattr__ or other mechanisms. This test verifies that constants
        # have correct initial values and types.

        # Verify initial values are correct
        assert constants.DEFAULT_MAX_FILE_LINES == 400
        assert ".py" in constants.CODE_FILE_EXTENSIONS
        assert constants.PROJECTID_FILENAME == "projectid"

        # Verify types are correct
        assert isinstance(constants.CODE_FILE_EXTENSIONS, set)
        assert isinstance(constants.DEFAULT_MAX_FILE_LINES, int)
        assert isinstance(constants.PROJECTID_FILENAME, str)
