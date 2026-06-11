"""
Structured JSON/YAML handlers: routing, pointer/path edits, validation order, dry_run.

Consolidated from tests/test_json_handler.py and tests/test_yaml_handler.py (step 20).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from ai_editor.core.file_handlers import (
    HANDLER_JSON,
    HANDLER_YAML,
    FileHandlerRequest,
    JsonFileHandler,
    TextFileHandler,
    YamlFileHandler,
    resolve_handler,
)
from ai_editor.core.file_handlers.yaml_handler import (
    delete_at_path,
    get_at_path,
    parse_yaml_path,
)


# --- Registry: structured suffixes do not route to text ---


def test_resolve_json_handler() -> None:
    assert resolve_handler("dir/config.json", "replace") == HANDLER_JSON
    assert resolve_handler("dir/config.json", "read") == HANDLER_JSON


def test_resolve_yaml_handler() -> None:
    assert resolve_handler("dir/config.yaml", "replace") == HANDLER_YAML
    assert resolve_handler("dir/config.yml", "read") == HANDLER_YAML


# --- Text handler must not apply line replacement to .json / .yaml / .yml ---


def test_text_handler_rejects_json_path_for_replace(tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text("{}\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="x.json",
        handler_id="text",
        operation="replace",
        extra={
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "new_lines": [],
        },
    )
    out = TextFileHandler().replace(req)
    assert out.success is False
    assert "plain-text" in out.message.lower() or "suffix" in out.message.lower()


def test_text_handler_rejects_yaml_suffix_for_replace(tmp_path: Path) -> None:
    f = tmp_path / "x.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="x.yaml",
        handler_id="text",
        operation="replace",
        extra={
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "new_lines": [],
        },
    )
    out = TextFileHandler().replace(req)
    assert out.success is False
    assert "plain-text" in out.message.lower() or "suffix" in out.message.lower()


def test_text_handler_rejects_yml_suffix_for_replace(tmp_path: Path) -> None:
    f = tmp_path / "x.yml"
    f.write_text("a: 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="x.yml",
        handler_id="text",
        operation="replace",
        extra={
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "new_lines": [],
        },
    )
    out = TextFileHandler().replace(req)
    assert out.success is False
    assert "plain-text" in out.message.lower() or "suffix" in out.message.lower()


# --- JSON handler rejects plain-text line keys ---


def test_json_read_rejects_line_range_params(tmp_path: Path) -> None:
    f = tmp_path / "a.json"
    f.write_text('{"k": 1}\n', encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="a.json",
        handler_id="json",
        operation="read",
        extra={"absolute_path": f, "start_line": 1, "end_line": 1},
    )
    out = JsonFileHandler().read(req)
    assert out.success is False
    assert "line" in out.message.lower() or "json_pointer" in out.message.lower()


def test_json_replace_rejects_line_range_params(tmp_path: Path) -> None:
    f = tmp_path / "linekeys.json"
    f.write_text('{"x": 1}\n', encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="linekeys.json",
        handler_id="json",
        operation="replace",
        extra={
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "new_lines": ["foo"],
            "operations": [{"action": "replace", "json_pointer": "/x", "value": 2}],
        },
    )
    with patch(
        "ai_editor.core.file_handlers.json_handler.save_json_tree_to_file",
    ) as save_mock:
        out = JsonFileHandler().replace(req)
    assert out.success is False
    assert "line" in out.message.lower() or "json_pointer" in out.message.lower()
    save_mock.assert_not_called()


def test_json_read_loads_nodes(tmp_path: Path) -> None:
    f = tmp_path / "b.json"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="b.json",
        handler_id="json",
        operation="read",
        extra={"absolute_path": f},
    )
    out = JsonFileHandler().read(req)
    assert out.success is True
    assert out.data.get("total_nodes", 0) >= 1
    assert out.data.get("root_node_id")


# --- JSON replace: json_pointer / node_id semantics ---


def test_json_replace_invalid_node_validates_before_save(tmp_path: Path) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"x": 1}\n', encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    db = MagicMock()
    root = tmp_path
    req = FileHandlerRequest(
        project_id="p1",
        file_path="c.json",
        handler_id="json",
        operation="replace",
        extra={
            "absolute_path": f,
            "database": db,
            "root_dir": root,
            "operations": [
                {"action": "replace", "node_id": "not-a-real-node", "value": 2},
            ],
        },
    )
    with patch(
        "ai_editor.core.file_handlers.json_handler.save_json_tree_to_file",
    ) as save_mock:
        save_mock.side_effect = AssertionError("save_json_tree_to_file must not run")
        out = JsonFileHandler().replace(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == raw_before
    save_mock.assert_not_called()


def test_json_replace_invalid_json_pointer_validates_before_save(
    tmp_path: Path,
) -> None:
    f = tmp_path / "ptr.json"
    f.write_text('{"x": 1}\n', encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    db = MagicMock()
    root = tmp_path
    req = FileHandlerRequest(
        project_id="p1",
        file_path="ptr.json",
        handler_id="json",
        operation="replace",
        extra={
            "absolute_path": f,
            "database": db,
            "root_dir": root,
            "operations": [
                {"action": "replace", "json_pointer": "/missing/key", "value": 0},
            ],
        },
    )
    with patch(
        "ai_editor.core.file_handlers.json_handler.save_json_tree_to_file",
    ) as save_mock:
        save_mock.side_effect = AssertionError("save_json_tree_to_file must not run")
        out = JsonFileHandler().replace(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == raw_before
    save_mock.assert_not_called()


def test_json_replace_dry_run_leaves_file_unchanged(tmp_path: Path) -> None:
    f = tmp_path / "d.json"
    f.write_text('{"x": 1}\n', encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="d.json",
        handler_id="json",
        operation="replace",
        dry_run=True,
        diff=True,
        extra={
            "absolute_path": f,
            "operations": [
                {"action": "replace", "json_pointer": "/x", "value": 99},
            ],
        },
    )
    with patch(
        "ai_editor.core.file_handlers.json_handler.save_json_tree_to_file",
    ) as save_mock:
        out = JsonFileHandler().replace(req)
    assert out.success is True
    assert out.dry_run is True
    assert f.read_text(encoding="utf-8") == raw_before
    save_mock.assert_not_called()
    assert "diff" in out.data
    ser = out.data.get("serialized", "")
    assert '"x"' in ser
    parsed = json.loads(ser)
    assert parsed["x"] == 99


def test_json_save_dry_run_serializes_without_write(tmp_path: Path) -> None:
    f = tmp_path / "save.json"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="save.json",
        handler_id="json",
        operation="save",
        dry_run=True,
        diff=True,
        extra={
            "absolute_path": f,
            "content": '{"a": 2}',
        },
    )
    out = JsonFileHandler().save(req)
    assert out.success is True
    assert f.read_text(encoding="utf-8") == raw_before
    ser = out.data.get("serialized", "")
    assert json.loads(ser) == {"a": 2}
    assert "diff" in out.data


def test_json_handler_registration_ready() -> None:
    h = JsonFileHandler()
    assert h.handler_id == "json"
    assert h.ready_for_all_operations_schema()


# --- YAML path helpers ---


def test_parse_yaml_path_root_and_indices() -> None:
    assert parse_yaml_path("") == []
    assert parse_yaml_path("/a/0") == ["a", "0"]
    assert parse_yaml_path("/d~1e") == ["d/e"]
    assert parse_yaml_path("/d~0e") == ["d~e"]


def test_get_at_path() -> None:
    doc = {"x": [{"y": 2}]}
    assert get_at_path(doc, "") is doc
    assert get_at_path(doc, "/x/0/y") == 2


def test_delete_at_path() -> None:
    doc = {"a": 1, "b": 2}
    delete_at_path(doc, "/a")
    assert doc == {"b": 2}


# --- YAML handler rejects line keys ---


def test_yaml_read_rejects_line_range_params(tmp_path: Path) -> None:
    f = tmp_path / "a.yaml"
    f.write_text("k: 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="a.yaml",
        handler_id="yaml",
        operation="read",
        extra={"absolute_path": f, "start_line": 1, "end_line": 1},
    )
    out = YamlFileHandler().read(req)
    assert out.success is False
    assert "line" in out.message.lower() or "yaml_path" in out.message.lower()


def test_yaml_read_document_and_paths(tmp_path: Path) -> None:
    f = tmp_path / "b.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="b.yaml",
        handler_id="yaml",
        operation="read",
        extra={"absolute_path": f},
    )
    out = YamlFileHandler().read(req)
    assert out.success is True
    assert out.data.get("document") == {"a": 1}
    assert "" in (out.data.get("paths") or [])
    assert "/a" in (out.data.get("paths") or [])


# --- YAML replace: yaml_path semantics; fail before backup / persist ---


def test_yaml_replace_invalid_path_before_backup(tmp_path: Path) -> None:
    f = tmp_path / "c.yaml"
    f.write_text("x: 1\n", encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    root = tmp_path
    db = MagicMock()
    req = FileHandlerRequest(
        project_id="p1",
        file_path="c.yaml",
        handler_id="yaml",
        operation="replace",
        extra={
            "absolute_path": f,
            "root_dir": root,
            "database": db,
            "normalized_path": "c.yaml",
            "yaml_path": "/x/nested",
            "value": 9,
        },
    )
    with patch(
        "ai_editor.core.file_handlers.yaml_handler.BackupManager.create_backup",
    ) as bu:
        bu.side_effect = AssertionError("backup must not run for bad path")
        with patch(
            "ai_editor.core.file_handlers.yaml_handler.persist_plain_text_file_metadata",
        ) as persist:
            persist.side_effect = AssertionError("persist must not run for bad path")
            out = YamlFileHandler().replace(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == raw_before
    bu.assert_not_called()


def test_yaml_replace_invalid_pointer_syntax_before_backup(tmp_path: Path) -> None:
    f = tmp_path / "d.yaml"
    f.write_text("x: 1\n", encoding="utf-8")
    root = tmp_path
    req = FileHandlerRequest(
        project_id="p1",
        file_path="d.yaml",
        handler_id="yaml",
        operation="replace",
        extra={
            "absolute_path": f,
            "root_dir": root,
            "yaml_path": "no-leading-slash",
            "value": 1,
        },
    )
    with patch(
        "ai_editor.core.file_handlers.yaml_handler.BackupManager.create_backup",
    ) as bu:
        out = YamlFileHandler().replace(req)
    assert out.success is False
    bu.assert_not_called()


def test_yaml_replace_dry_run_leaves_file_unchanged(tmp_path: Path) -> None:
    f = tmp_path / "e.yaml"
    f.write_text("x: 1\n", encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="e.yaml",
        handler_id="yaml",
        operation="replace",
        dry_run=True,
        diff=True,
        extra={
            "absolute_path": f,
            "root_dir": tmp_path,
            "yaml_path": "/x",
            "value": 99,
        },
    )
    with patch(
        "ai_editor.core.file_handlers.yaml_handler.BackupManager.create_backup",
    ) as bu:
        out = YamlFileHandler().replace(req)
    assert out.success is True
    assert out.dry_run is True
    assert f.read_text(encoding="utf-8") == raw_before
    bu.assert_not_called()
    assert "diff" in out.data
    ser = out.data.get("serialized", "")
    doc = yaml.safe_load(ser)
    assert doc["x"] == 99


def test_yaml_save_round_trip_dry_run(tmp_path: Path) -> None:
    f = tmp_path / "f.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="f.yaml",
        handler_id="yaml",
        operation="save",
        dry_run=True,
        extra={
            "absolute_path": f,
            "root_dir": tmp_path,
            "content": "a: 2\n",
        },
    )
    raw = f.read_text(encoding="utf-8")
    out = YamlFileHandler().save(req)
    assert out.success is True
    assert f.read_text(encoding="utf-8") == raw
    ser = out.data.get("serialized", "")
    assert yaml.safe_load(ser) == {"a": 2}, "dry_run must expose serialized after state"


def test_yaml_nested_replace_yaml_path_dry_run(tmp_path: Path) -> None:
    f = tmp_path / "nest.yaml"
    f.write_text("root:\n  k: old\n", encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="nest.yaml",
        handler_id="yaml",
        operation="replace",
        dry_run=True,
        diff=False,
        extra={
            "absolute_path": f,
            "root_dir": tmp_path,
            "yaml_path": "/root/k",
            "value": "new",
        },
    )
    out = YamlFileHandler().replace(req)
    assert out.success is True
    assert f.read_text(encoding="utf-8") == raw_before
    doc = yaml.safe_load(out.data["serialized"])
    assert doc["root"]["k"] == "new"


def test_delete_path_invalid_before_backup(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text("x: 1\n", encoding="utf-8")
    raw_before = f.read_text(encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="g.yaml",
        handler_id="yaml",
        operation="delete",
        extra={
            "absolute_path": f,
            "root_dir": tmp_path,
            "yaml_path": "/missing",
        },
    )
    with patch(
        "ai_editor.core.file_handlers.yaml_handler.BackupManager.create_backup",
    ) as bu:
        bu.side_effect = AssertionError("backup must not run")
        out = YamlFileHandler().delete(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == raw_before
    bu.assert_not_called()


def test_yaml_handler_registration_ready() -> None:
    h = YamlFileHandler()
    assert h.handler_id == "yaml"
    assert h.ready_for_all_operations_schema()
