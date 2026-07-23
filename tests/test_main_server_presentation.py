"""Tests for server title/description/version resolution from config."""

from __future__ import annotations

from typing import Any, Dict

from ai_editor.commands.universal_file_edit.workflow_brief import (
    SERVER_HELP_DESCRIPTION,
    SERVER_LIST_DESCRIPTION,
)
from ai_editor.main_server_presentation import (
    resolve_server_presentation,
    resolve_server_presentation_legacy,
    sync_registration_presentation,
)


def test_resolve_from_server_presentation() -> None:
    from importlib.metadata import version as pkg_version

    app_config = {
        "server_presentation": {
            "title": "My Server",
            "description": "Custom help description",
            "list_description": "Custom list blurb",
            "version": "2.3.4",
        },
        "registration": {"server_id": "ai-editor-server"},
    }
    pres = resolve_server_presentation(app_config)
    assert pres.title == "My Server"
    assert pres.help_description == "Custom help description"
    assert pres.list_description == "Custom list blurb"

    assert pres.version == pkg_version("ai-editor")

    title, description, version = resolve_server_presentation_legacy(app_config)
    assert title == "My Server"
    assert description == "Custom help description"
    assert version == pkg_version("ai-editor")


def test_default_tiers_differ() -> None:
    pres = resolve_server_presentation({})
    assert pres.list_description == SERVER_LIST_DESCRIPTION
    assert pres.help_description == SERVER_HELP_DESCRIPTION
    assert len(pres.list_description) < len(pres.help_description)
    assert "Ruff" in pres.help_description


def test_sync_registration_for_proxy() -> None:
    from importlib.metadata import version as pkg_version

    app_config: Dict[str, Any] = {
        "server_presentation": {
            "title": "My Server",
            "description": "Help tier text",
            "list_description": "List tier text",
            "version": "9.9.9",
        },
        "registration": {"server_id": "ai-editor-server", "enabled": True},
    }
    sync_registration_presentation(app_config)
    reg = app_config["registration"]
    assert reg["metadata"]["description"] == "List tier text"
    assert reg["metadata"]["help_description"] == "Help tier text"
    assert reg["metadata"]["version"] == pkg_version("ai-editor")
    assert reg["metadata"]["server_name"] == "My Server"
    assert reg["description"] == "List tier text"
    assert reg["server_name"] == "My Server"


def test_version_always_from_package_ignoring_config() -> None:
    """Version must always reflect the installed package, never a config override.

    Regression test for bug 8fefd757: help/tool_info and proxy registration
    metadata reported a stale hardcoded config version ("1.0.61") while health
    (which reads importlib.metadata directly) reported the correct live
    version. resolve_server_presentation must ignore any config-supplied
    version and always derive it from the installed ai-editor package.
    """
    from importlib.metadata import version as pkg_version

    expected = pkg_version("ai-editor")
    stale_config: Dict[str, Any] = {
        "server_presentation": {"version": "1.0.61"},
        "registration": {
            "version": "1.0.61",
            "metadata": {"version": "1.0.61"},
        },
    }
    pres = resolve_server_presentation(stale_config)
    assert pres.version == expected
    assert pres.version != "1.0.61"

    sync_registration_presentation(stale_config)
    assert stale_config["registration"]["metadata"]["version"] == expected
    assert stale_config["registration"]["version"] == expected
