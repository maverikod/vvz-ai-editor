"""Tests for server title/description/version resolution from config."""

from __future__ import annotations

from ai_editor.main_server_presentation import (
    resolve_server_presentation,
    sync_registration_presentation,
)


def test_resolve_from_server_presentation() -> None:
    app_config = {
        "server_presentation": {
            "title": "My Server",
            "description": "Custom description",
            "version": "2.3.4",
        },
        "registration": {"server_id": "ai-editor-server"},
    }
    title, description, version = resolve_server_presentation(app_config)
    assert title == "My Server"
    assert description == "Custom description"
    assert version == "2.3.4"


def test_sync_registration_for_proxy() -> None:
    app_config = {
        "server_presentation": {
            "title": "My Server",
            "description": "For proxy",
            "version": "9.9.9",
        },
        "registration": {"server_id": "ai-editor-server", "enabled": True},
    }
    sync_registration_presentation(app_config)
    reg = app_config["registration"]
    assert reg["metadata"]["description"] == "For proxy"
    assert reg["metadata"]["version"] == "9.9.9"
    assert reg["metadata"]["server_name"] == "My Server"
    assert reg["description"] == "For proxy"
    assert reg["server_name"] == "My Server"
