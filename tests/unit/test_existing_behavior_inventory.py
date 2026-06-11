"""
Unit tests for existing_behavior_inventory.yaml (T-001/A-001).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

INVENTORY_PATH = (
    Path(__file__).parent.parent.parent
    / "docs/plans/2026-05-21-paginated-search-results/existing_behavior_inventory.yaml"
)

REQUIRED_COMMAND_NAMES = [
    "fs_grep",
    "fulltext_search",
    "semantic_search",
    "project_cross_search",
    "search_start",
    "search_get_page",
    "search_get_status",
    "search_cancel",
    "search_close",
]

LEGACY_COMMANDS = {
    "fs_grep",
    "fulltext_search",
    "semantic_search",
    "project_cross_search",
}
LIFECYCLE_COMMANDS = {
    "search_start",
    "search_get_page",
    "search_get_status",
    "search_cancel",
    "search_close",
}
CONTRACT_FIELDS = {"job_id", "block_position", "index_url"}


@pytest.fixture(scope="module")
def inventory() -> dict:
    assert INVENTORY_PATH.is_file(), f"Inventory not found: {INVENTORY_PATH}"
    return yaml.safe_load(INVENTORY_PATH.read_text())


def test_all_required_command_names_present(inventory: dict) -> None:
    names = {cmd["name"] for cmd in inventory["commands"]}
    for required in REQUIRED_COMMAND_NAMES:
        assert required in names, f"Missing command: {required}"


def test_legacy_commands_have_nonempty_existing(inventory: dict) -> None:
    for cmd in inventory["commands"]:
        if cmd["name"] in LEGACY_COMMANDS:
            assert cmd.get("existing"), f"{cmd['name']}.existing must be non-empty"


def test_lifecycle_commands_document_session_backed_new_behaviors(
    inventory: dict,
) -> None:
    for cmd in inventory["commands"]:
        if cmd["name"] in LIFECYCLE_COMMANDS:
            new_text = " ".join(str(b) for b in (cmd.get("new") or []))
            assert "job_id" in new_text, f"{cmd['name']}.new must mention job_id"


def test_meta_contract_decision_rejects_cursor(inventory: dict) -> None:
    cd = inventory["meta"]["contract_decision"]
    assert cd["cursor_used"] is False, "cursor_used must be false"
    fields = set(cd["canonical_paging_fields"])
    assert (
        CONTRACT_FIELDS <= fields
    ), f"Missing contract fields: {CONTRACT_FIELDS - fields}"


def test_no_tbd_or_todo_in_inventory(inventory: dict) -> None:
    raw = INVENTORY_PATH.read_text().upper()
    assert "TBD" not in raw, "Inventory must not contain TBD"
    assert "TODO" not in raw, "Inventory must not contain TODO"
