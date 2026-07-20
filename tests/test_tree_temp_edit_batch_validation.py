"""Format-neutral validation for structured tree-temp edit operations."""

from __future__ import annotations

import pytest

from ai_editor.commands.universal_file_edit.tree_temp_edit_batch import (
    _serialize_insert_value,
    validate_tree_temp_operation,
)


@pytest.mark.parametrize("handler_id", ["json", "yaml", "ini", "toml"])
@pytest.mark.parametrize(
    "operation",
    [
        {"action": "insert", "parent_json_pointer": "/section", "key": "name", "value": "v"},
        {"action": "replace", "node_ref": "/section/name", "value": "new"},
        {"action": "delete", "json_pointer": "/section/name"},
    ],
)
def test_structured_key_operations_are_format_neutral(
    handler_id: str, operation: dict[str, object]
) -> None:
    """Structured config handlers use the same public operation contract."""
    validate_tree_temp_operation(operation, handler_id)


@pytest.mark.parametrize(
    "operation",
    [
        {"action": "insert", "key": "", "value": 1},
        {
            "action": "insert",
            "value": 1,
            "before_key": "a",
            "after_key": "b",
        },
        {"action": "replace", "value": 1},
        {"action": "delete"},
    ],
)
def test_structured_key_operations_reject_invalid_shape(
    operation: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        validate_tree_temp_operation(operation, "yaml")


@pytest.mark.parametrize("handler_id", ["text", "python"])
def test_non_structured_handlers_are_rejected(handler_id: str) -> None:
    operation = {"action": "delete", "json_pointer": "/section/name"}
    with pytest.raises(ValueError, match="Unsupported handler"):
        validate_tree_temp_operation(operation, handler_id)


@pytest.mark.parametrize("handler_id", ["ini", "toml"])
def test_structured_handlers_reach_backend_serializer(handler_id: str) -> None:
    """Public validation admits config formats with concrete serializers."""
    operation = {"action": "delete", "json_pointer": "/section/name"}
    validate_tree_temp_operation(operation, handler_id)
    assert _serialize_insert_value(handler_id, "value").strip() == "value"
