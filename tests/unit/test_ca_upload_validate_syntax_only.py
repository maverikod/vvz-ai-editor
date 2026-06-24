"""Unit test: upload_session_file_content passes validate_syntax_only=True to CA.

Regression guard for TZ-AIEDITOR-COMMIT-STALE-VALIDATION-001 (D-1/A-1).

The CA's project_file_transfer_upload_save validates the session state it holds
(the pre-edit original), not the uploaded content.  Passing validate_syntax_only=True
instructs the CA to skip semantic validation (docstrings, etc.), which resolves the
false UPSTREAM_UPLOAD_FAILED that arose when the CA rejected a valid post-edit upload.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient


def _make_client() -> CodeAnalysisClient:
    """Build a CodeAnalysisClient with a stub _section so __init__ doesn't call CA."""
    with patch(
        "ai_editor.core.upstream.code_analysis_client._load_ca_section",
        return_value={"host": "localhost", "port": 15010},
    ):
        with patch(
            "ai_editor.core.upstream.code_analysis_client._build_jsonrpc_kwargs",
            return_value={"host": "localhost", "port": 15010},
        ):
            return CodeAnalysisClient()


def test_upload_session_file_content_passes_validate_syntax_only() -> None:
    """upload_session_file_content must include validate_syntax_only=True in the RPC call.

    This prevents the CA from running semantic validation (e.g. docstrings) against its
    stale in-memory session state instead of the newly uploaded content.
    """
    client = _make_client()

    captured: dict = {}

    def _fake_call(cmd: str, params: dict) -> dict:
        captured["cmd"] = cmd
        captured["params"] = dict(params)
        return {"content_bytes": b"accepted"}

    with patch(
        "ai_editor.core.upstream.code_analysis_client.upload_bytes_transfer_id",
        return_value="tid-001",
    ):
        with patch(
            "ai_editor.core.upstream.code_analysis_client.resolve_file_id_for_path",
            return_value="fid-001",
        ):
            with patch.object(client, "call", side_effect=_fake_call):
                result = client.upload_session_file_content(
                    session_id="sess-1",
                    project_id="proj-1",
                    file_path="src/foo.py",
                    content=b"x = 1\n",
                )

    assert captured["cmd"] == "project_file_transfer_upload_save"
    assert captured["params"].get("validate_syntax_only") is True, (
        "validate_syntax_only must be True so the CA skips stale-state docstring "
        "validation; without it the CA rejects valid uploads with pre-edit line numbers"
    )
    assert result == b"accepted"
