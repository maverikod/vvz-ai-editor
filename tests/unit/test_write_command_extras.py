"""Tests for write optional format_python and CA verify helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_editor.commands.universal_file_edit.write_command_extras import (
    verify_ca_readback,
)
from ai_editor.core.code_quality.formatter import format_python_source_text


def test_format_python_source_text_adds_trailing_newline_style() -> None:
    src = "x=1\n"
    formatted, err = format_python_source_text(src)
    assert err is None
    assert "x = 1" in formatted


def test_verify_ca_readback_match() -> None:
    client = MagicMock()
    client.download_without_lock.return_value = b"hello\n"
    out = verify_ca_readback(
        client,
        project_id="p",
        file_path="a.txt",
        expected_bytes=b"hello\n",
    )
    assert out["verified"] is True
    client.download_without_lock.assert_called_once_with(
        project_id="p",
        file_path="a.txt",
    )


def test_verify_ca_readback_mismatch() -> None:
    client = MagicMock()
    client.download_without_lock.return_value = b"other\n"
    out = verify_ca_readback(
        client,
        project_id="p",
        file_path="a.txt",
        expected_bytes=b"hello\n",
    )
    assert out["verified"] is False
