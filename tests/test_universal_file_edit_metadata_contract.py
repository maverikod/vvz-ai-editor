"""Contract checks for the public universal_file_edit operation catalog."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.editor_info_content import build_editor_info_payload
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from ai_editor.commands.universal_file_edit.errors import (
    PUBLIC_EDIT_OPERATION,
    PUBLIC_EDIT_OPERATION_TYPES,
    public_edit_operation_remediation,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from tests.thin_editor_ca_mocks import edit_guard_context


def test_metadata_matches_callable_format_boundaries() -> None:
    metadata = UniversalFileEditCommand.metadata()
    description = metadata["detailed_description"]
    operation_description = metadata["parameters"]["operations"]["description"]

    assert "Structured config (.json, .yaml, .yml, .ini, .cfg, .toml)" in description
    assert (
        "Structured tree operations are replace | insert | delete | move."
        in description
    )
    assert "INI/TOML use the same node_ref/json_pointer" in description
    assert "structured types are replace, insert, delete, move" in operation_description


def test_metadata_advertises_ini_toml_node_remediation() -> None:
    metadata = UniversalFileEditCommand.metadata()
    description = metadata["detailed_description"]

    assert "the handler preserves their source format" in description


def test_diagnostic_remediation_uses_public_callable_edit_catalog() -> None:
    metadata = UniversalFileEditCommand.metadata()
    operation_description = metadata["parameters"]["operations"]["description"]
    remediation = public_edit_operation_remediation()

    assert PUBLIC_EDIT_OPERATION in remediation
    assert "replace_range" not in remediation
    assert all(
        operation in operation_description for operation in PUBLIC_EDIT_OPERATION_TYPES
    )


def test_info_metadata_advertises_ruff_python_validation_gate() -> None:
    payload = build_editor_info_payload()
    markdown = payload["markdown"]

    assert (
        "Python validation: black-parseable, flake8, Ruff, mypy, docstrings."
        in markdown
    )
    assert "black-parseable, flake8, mypy, docstrings" not in markdown


def test_write_metadata_advertises_ruff_python_validation_gate() -> None:
    metadata = UniversalFileWriteCommand.metadata()
    rendered = repr(metadata)

    assert "black-parseable, flake8, Ruff, mypy" in rendered
    assert "flake8/Ruff/mypy/docstring" in rendered
    assert "black-parseable, flake8, mypy" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("format_group", "operations", "handler_name"),
    [
        (
            FORMAT_SIDECAR,
            [
                {"type": "replace", "node_id": "1", "code_lines": ["x = 1"]},
                {
                    "type": "insert",
                    "parent_node_id": "__root__",
                    "position": "last",
                    "code_lines": ["x = 1"],
                },
                {"type": "delete", "node_id": "1"},
                {
                    "type": "move",
                    "node_id": "1",
                    "parent_node_id": "__root__",
                    "position": "last",
                },
            ],
            "_apply_sidecar",
        ),
        (
            FORMAT_TREE_TEMP,
            [
                {"type": "replace", "node_ref": "1", "value": "updated"},
                {
                    "type": "insert",
                    "parent_json_pointer": "/section",
                    "key": "name",
                    "value": "new",
                },
                {"type": "delete", "node_ref": "1"},
                {
                    "type": "move",
                    "node_ref": "1",
                    "parent_node_id": "1",
                    "position": "last",
                },
            ],
            "_apply_tree_temp",
        ),
        (
            FORMAT_TEXT,
            [
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "updated",
                },
                {"type": "insert", "position": "last", "content": "new"},
                {"type": "delete", "start_line": 1, "end_line": 1},
                {"type": "move", "node_ref": "0", "position": "last"},
            ],
            "_apply_text",
        ),
    ],
)
async def test_advertised_operations_are_callable_via_public_edit_api(
    tmp_path, format_group, operations, handler_name
) -> None:
    """Exercise every advertised operation class through execute(), not metadata text."""
    sid = "metadata-contract-session"
    draft_path = tmp_path / "draft"
    draft_path.write_text("draft\n", encoding="utf-8")
    session = SimpleNamespace(
        format_group=format_group,
        draft_path=draft_path,
        tree_id="tree-contract",
        read_only=False,
        read_only_reason="",
        is_invalid=False,
        modified=False,
    )
    command = UniversalFileEditCommand()
    apply_handler = Mock(return_value=SuccessResult(data={"success": True}))

    with (
        edit_guard_context(),
        patch(
            "ai_editor.commands.universal_file_edit.edit_command.get_session",
            return_value=session,
        ),
        patch.object(command, handler_name, apply_handler),
        patch(
            "ai_editor.commands.universal_file_edit.edit_command.validate_sidecar_nested_batch",
            return_value=None,
        ),
    ):
        for operation in operations:
            result = await command.execute(
                project_id="project",
                session_id=sid,
                operations=[operation],
            )
            assert isinstance(result, SuccessResult), operation

    assert apply_handler.call_count == len(operations)
    assert [call.args[1][0]["type"] for call in apply_handler.call_args_list] == [
        operation["type"] for operation in operations
    ]
