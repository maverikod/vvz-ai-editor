"""Schema/metadata alignment for MCP help-surface commands."""

from __future__ import annotations

import pytest

from ai_editor.commands.command_metadata_helpers import (
    REQUIRED_METADATA_KEYS,
    finalize_command_metadata,
    parameters_from_schema,
)
from ai_editor.commands.health_command import HealthCommand
from ai_editor.commands.info_command import InfoCommand
from ai_editor.commands.universal_file_edit.close_command import UniversalFileCloseCommand
from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
from ai_editor.commands.universal_file_edit.open_command import UniversalFileOpenCommand
from ai_editor.commands.universal_file_edit.search_command import UniversalFileSearchCommand
from ai_editor.commands.universal_file_edit.write_command import UniversalFileWriteCommand
from ai_editor.commands.universal_file_preview_command import UniversalFilePreviewCommand
from ai_editor.hooks import register_ai_editor_commands
from mcp_proxy_adapter.commands.command_registry import CommandRegistry

_HELP_SURFACE_COMMANDS = (
    InfoCommand,
    HealthCommand,
    UniversalFileOpenCommand,
    UniversalFileEditCommand,
    UniversalFileWriteCommand,
    UniversalFileCloseCommand,
    UniversalFilePreviewCommand,
    UniversalFileSearchCommand,
)


@pytest.mark.parametrize("cmd_cls", _HELP_SURFACE_COMMANDS, ids=lambda c: c.name)
def test_get_schema_is_valid_object(cmd_cls: type) -> None:
    schema = cmd_cls.get_schema()
    assert schema.get("type") == "object"
    assert "properties" in schema
    assert "required" in schema
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("cmd_cls", _HELP_SURFACE_COMMANDS, ids=lambda c: c.name)
def test_metadata_has_required_keys(cmd_cls: type) -> None:
    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    registered = reg.get_all_commands()[cmd_cls.name]
    meta = registered.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"{cmd_cls.name} metadata missing {key!r}"


@pytest.mark.parametrize("cmd_cls", _HELP_SURFACE_COMMANDS, ids=lambda c: c.name)
def test_metadata_parameters_match_schema(cmd_cls: type) -> None:
    schema = cmd_cls.get_schema()
    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    meta = reg.get_all_commands()[cmd_cls.name].metadata()
    expected = parameters_from_schema(schema)
    assert set(meta["parameters"].keys()) == set(expected.keys())
    for key, spec in expected.items():
        actual = meta["parameters"][key]
        assert actual["description"] == spec["description"]
        assert actual["type"] == spec["type"]
        assert actual["required"] == spec["required"]


@pytest.mark.parametrize("cmd_cls", _HELP_SURFACE_COMMANDS, ids=lambda c: c.name)
def test_usage_examples_use_schema_keys_only(cmd_cls: type) -> None:
    schema = cmd_cls.get_schema()
    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    meta = reg.get_all_commands()[cmd_cls.name].metadata()
    allowed = set((schema.get("properties") or {}).keys())
    for ex in meta.get("usage_examples") or []:
        cmd = ex.get("command")
        if isinstance(cmd, dict) and cmd:
            assert set(cmd.keys()) <= allowed, (
                f"{cmd_cls.name} example uses unknown keys: {set(cmd.keys()) - allowed}"
            )


def test_preview_schema_documents_line_pagination() -> None:
    schema = UniversalFilePreviewCommand.get_schema()
    props = schema["properties"]
    assert "line" in props["preview_offset"]["description"].lower()
    assert "invalid" in props["preview_lines"]["description"].lower() or "fallback" in (
        props["preview_lines"]["description"].lower()
    )
    assert props["max_chars"]["default"] == 32_000


def test_preview_metadata_error_codes_match_implementation() -> None:
    meta = finalize_command_metadata(
        UniversalFilePreviewCommand,
        UniversalFilePreviewCommand.metadata(),
    )
    codes = set(meta["error_cases"].keys())
    assert "REQUIRES_LINE_ADDRESSING" in codes
    assert "REQUIRES_IDENTIFIER_ADDRESSING" in codes
    assert "OPEN_FILE_USE_WORKSPACE_PREVIEW" in codes


def test_metadata_documents_identifier_types() -> None:
    from ai_editor.commands.editor_info_content import build_editor_info_payload
    from ai_editor.commands.universal_file_edit.edit_command import UniversalFileEditCommand
    from ai_editor.commands.universal_file_edit.search_command import UniversalFileSearchCommand

    preview = finalize_command_metadata(
        UniversalFilePreviewCommand,
        UniversalFilePreviewCommand.metadata(),
    )
    edit = finalize_command_metadata(
        UniversalFileEditCommand,
        UniversalFileEditCommand.metadata(),
    )
    search = finalize_command_metadata(
        UniversalFileSearchCommand,
        UniversalFileSearchCommand.metadata(),
    )
    info = build_editor_info_payload()

    for text in (
        preview["detailed_description"],
        edit["detailed_description"],
        search["detailed_description"],
    ):
        assert "short_id" in text.lower()
        assert "uuid" in text.lower() or "search" in text.lower()

    assert "short_id" in info["format_groups"]["sidecar"]["preview_node_ref"].lower()
    assert "uuid" in info["format_groups"]["sidecar"]["preview_node_ref"].lower()
    assert "short_id" in info["format_groups"]["tree-temp"]["preview_node_ref"].lower()

    # Stale docs claimed preview always returns UUID for Python
    assert "stable uuid" not in preview["detailed_description"].lower().split("legacy")[0]
