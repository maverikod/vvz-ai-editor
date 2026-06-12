"""
Tests for host-side config preflight (ai-editor-docker package).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _REPO_ROOT / "docker" / "pkg" / "config_preflight.py"


@pytest.fixture
def preflight_script() -> Path:
    if not _PREFLIGHT.is_file():
        pytest.skip("docker/pkg/config_preflight.py not found")
    return _PREFLIGHT


def test_preflight_rejects_unset_placeholders(
    tmp_path: Path, preflight_script: Path
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "server": {"advertised_host": "${AI_EDITOR_ADVERTISED_HOST}"},
                "registration": {
                    "register_url": (
                        "https://${AI_EDITOR_REGISTRATION_HOST}:"
                        "${AI_EDITOR_REGISTRATION_PORT}/register"
                    )
                },
                "code_analysis_server": {
                    "host": "${AI_EDITOR_CODE_ANALYSIS_HOST}",
                    "port": 15010,
                },
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(preflight_script), str(cfg)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "AI_EDITOR_ADVERTISED_HOST" in result.stderr


def test_preflight_accepts_resolved_env(
    tmp_path: Path, preflight_script: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "server": {"advertised_host": "${AI_EDITOR_ADVERTISED_HOST}"},
                "code_analysis_server": {
                    "host": "${AI_EDITOR_CODE_ANALYSIS_HOST}",
                    "port": 15010,
                },
            }
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "AI_EDITOR_ADVERTISED_HOST": "10.0.0.2",
        "AI_EDITOR_CODE_ANALYSIS_HOST": "10.0.0.3",
    }
    result = subprocess.run(
        [sys.executable, str(preflight_script), str(cfg)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
