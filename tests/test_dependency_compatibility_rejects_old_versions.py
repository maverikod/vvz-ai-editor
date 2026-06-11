"""Compatibility checks must fail for old queue dependencies."""

from __future__ import annotations

import pytest

from ai_editor.core import dependency_compat


def test_dependency_compatibility_rejects_old_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {
        "ai-editor": "1.0.0",
        "mcp-proxy-adapter": "0.0.1",
        "queuemgr": "0.0.1",
    }

    def _fake_version(distribution: str) -> str:
        return versions[distribution]

    monkeypatch.setattr(dependency_compat.metadata, "version", _fake_version)

    with pytest.raises(RuntimeError):
        dependency_compat.assert_queue_dependencies_compatible(queue_enabled=True)
