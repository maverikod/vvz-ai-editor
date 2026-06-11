"""
Tests for ai_editor.core.file_handlers.registry (config-driven routing).

Routing expectations are checked against ``list_handler_mappings()`` and helpers
exported from ``ai_editor.core.file_handlers.registry`` — extension tables
are not duplicated in this module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

import pytest

from ai_editor.core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    OPERATIONS,
    RegistryError,
    get_handler_schema,
    list_handler_mappings,
    resolve_handler,
    validate_supported,
)


def _rows() -> List[Dict[str, str]]:
    """Single discovery path for parametrization (sorted for stable IDs)."""
    return sorted(list_handler_mappings(), key=lambda r: (r["handler_id"], r["suffix"]))


@pytest.mark.parametrize(
    "row",
    _rows(),
    ids=lambda r: f"{r['suffix']}->{r['handler_id']}",
)
def test_resolve_handler_matches_list_handler_mappings(row: Dict[str, str]) -> None:
    suffix, handler_id = row["suffix"], row["handler_id"]
    for op in sorted(OPERATIONS):
        assert resolve_handler(f"dir/file{suffix}", op) == handler_id
        assert resolve_handler(f"dir/FiLe{suffix.upper()}", op) == handler_id


def test_handler_suffix_groups_match_product_contract() -> None:
    """Public mapping groups match the supported text/json/yaml/python suffix sets."""
    groups: Dict[str, set[str]] = defaultdict(set)
    for r in list_handler_mappings():
        groups[r["handler_id"]].add(r["suffix"])
    by_id = {k: frozenset(v) for k, v in groups.items()}

    assert by_id[HANDLER_TEXT] == frozenset(
        {".md", ".txt", ".rst", ".adoc", ".jsonl", ".ndjson"}
    )
    assert by_id[HANDLER_JSON] == frozenset({".json"})
    assert by_id[HANDLER_YAML] == frozenset({".yaml", ".yml"})
    assert by_id[HANDLER_PYTHON] == frozenset({".py", ".pyi", ".pyw"})


def test_unknown_suffix_fails_closed() -> None:
    with pytest.raises(RegistryError) as exc:
        resolve_handler("file.unknown", "read")
    err = exc.value
    assert err.code == "UNSUPPORTED_FILE_EXTENSION"
    assert err.details["file_path"] == "file.unknown"
    assert err.details["suffix"] == ".unknown"


def test_pyproject_toml_unsupported_extension() -> None:
    with pytest.raises(RegistryError) as exc:
        resolve_handler("pyproject.toml", "read")
    err = exc.value
    assert err.code == "UNSUPPORTED_FILE_EXTENSION"
    assert err.details["suffix"] == ".toml"


def test_missing_suffix_fails_before_handler_resolution() -> None:
    with pytest.raises(RegistryError) as exc:
        validate_supported("README", "read")
    assert exc.value.code == "UNSUPPORTED_FILE_EXTENSION"
    assert exc.value.details["suffix"] == ""


def test_unsupported_operation_error_details() -> None:
    with pytest.raises(RegistryError) as exc:
        validate_supported("README.md", "patch")
    err = exc.value
    assert err.code == "UNSUPPORTED_FILE_OPERATION"
    assert err.details["file_path"] == "README.md"
    assert err.details["handler_id"] == ""


def test_get_handler_schema_text_read() -> None:
    schema = get_handler_schema(HANDLER_TEXT, "read")
    assert schema["type"] == "object"
    assert "properties" in schema


def test_unsupported_suffix_not_listed_in_discovery() -> None:
    known = {r["suffix"] for r in list_handler_mappings()}
    assert ".toml" not in known
