"""
Python file handler: registry routing, CST-only mutations, validation ordering.

Canonical suite (step 21). Replaces ``tests/test_python_handler.py``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.core.file_handlers import (
    HANDLER_PYTHON,
    HANDLER_TEXT,
    FileHandlerRequest,
    PythonFileHandler,
    TextFileHandler,
    resolve_handler,
)
from ai_editor.core.file_handlers.registry import OPERATIONS

NODE_UUID = "550e8400-e29b-41d4-a716-446655440001"


@pytest.mark.parametrize("suffix", (".py", ".pyi", ".pyw"))
@pytest.mark.parametrize("op", sorted(OPERATIONS))
def test_python_suffixes_resolve_to_python_handler(suffix: str, op: str) -> None:
    assert resolve_handler(f"pkg/mod{suffix}", op) == HANDLER_PYTHON
    assert resolve_handler(f"pkg/mod{suffix.upper()}", op) == HANDLER_PYTHON


@pytest.mark.parametrize("suffix", (".py", ".pyi", ".pyw"))
def test_python_suffixes_never_resolve_to_text_handler(suffix: str) -> None:
    assert resolve_handler(f"src/x{suffix}", "read") != HANDLER_TEXT


@pytest.mark.parametrize(
    "name",
    ("mod.py", "types.pyi", "gui.pyw"),
)
def test_resolve_python_files_all_suffixes(name: str) -> None:
    for op in sorted(OPERATIONS):
        assert resolve_handler(name, op) == HANDLER_PYTHON


@pytest.mark.parametrize(
    "suffix,body",
    (
        (".py", "a = 1\n"),
        (".pyi", "def f() -> int: ...\n"),
        (".pyw", "print(1)\n"),
    ),
)
def test_text_handler_rejects_python_paths_for_replace(
    tmp_path: Path, suffix: str, body: str
) -> None:
    f = tmp_path / f"x{suffix}"
    f.write_text(body, encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path=f.name,
        handler_id="text",
        operation="replace",
        extra={
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "new_lines": ["# x"],
        },
    )
    out = TextFileHandler().replace(req)
    assert out.success is False


def _root_with_file(tmp_path: Path, rel: str, content: str) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    root.mkdir()
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return root, f


@pytest.mark.parametrize(
    "line_keys",
    (
        {"start_line": 1, "end_line": 1, "new_lines": ["x"]},
        {"replacements": [{"start_line": 1, "end_line": 1, "new_lines": ["x"]}]},
    ),
)
def test_python_replace_rejects_raw_line_payloads(
    tmp_path: Path, line_keys: dict
) -> None:
    root, f = _root_with_file(tmp_path, "m.py", "a = 1\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="m.py",
        handler_id="python",
        operation="replace",
        extra={"root_path": root, "absolute_path": f, **line_keys},
    )
    out = PythonFileHandler().replace(req)
    assert out.success is False
    assert "line" in out.message.lower() or "cst" in out.message.lower()
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_python_save_rejects_raw_line_payloads(tmp_path: Path) -> None:
    root, f = _root_with_file(tmp_path, "m.py", "a = 1\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="m.py",
        handler_id="python",
        operation="save",
        extra={
            "root_path": root,
            "content": "b = 2\n",
            "start_line": 1,
            "end_line": 1,
        },
    )
    out = PythonFileHandler().save(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_python_delete_ops_path_rejects_raw_line_payloads(tmp_path: Path) -> None:
    root, f = _root_with_file(tmp_path, "m.py", "a = 1\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="m.py",
        handler_id="python",
        operation="delete",
        extra={
            "root_path": root,
            "absolute_path": f,
            "start_line": 1,
            "end_line": 1,
            "ops": [
                {
                    "selector": {"kind": "range", "start_line": 1, "end_line": 1},
                    "new_code": "",
                }
            ],
        },
    )
    out = PythonFileHandler().delete(req)
    assert out.success is False
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_python_replace_invalid_ops_empty_list_before_write(tmp_path: Path) -> None:
    root, f = _root_with_file(tmp_path, "m.py", "a = 1\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="m.py",
        handler_id="python",
        operation="replace",
        dry_run=False,
        extra={"root_path": root, "ops": []},
    )
    out = PythonFileHandler().replace(req)
    assert out.success is False
    assert out.code
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_python_replace_dry_run_range_selector_diff_no_write(tmp_path: Path) -> None:
    root, rel = tmp_path / "proj", "m.py"
    root.mkdir()
    f = root / rel
    f.write_text("a = 1\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path=rel,
        handler_id="python",
        operation="replace",
        dry_run=True,
        diff=True,
        extra={
            "root_path": root,
            "ops": [
                {
                    "selector": {"kind": "range", "start_line": 1, "end_line": 1},
                    "new_code": "b = 2\n",
                }
            ],
        },
    )
    out = PythonFileHandler().replace(req)
    assert out.success is True
    assert f.read_text(encoding="utf-8") == "a = 1\n"
    assert out.data.get("preview_only") is True
    assert out.data.get("diff")


def test_python_replace_dry_run_node_id_diff_no_write(tmp_path: Path) -> None:
    root, rel = tmp_path / "proj", "m.py"
    root.mkdir()
    f = root / rel
    f.write_text("a = 1\n", encoding="utf-8")
    meta = SimpleNamespace(start_line=1, start_col=0, end_line=1, end_col=5)
    tree = SimpleNamespace(metadata_map={NODE_UUID: meta})
    req = FileHandlerRequest(
        project_id="p1",
        file_path=rel,
        handler_id="python",
        operation="replace",
        dry_run=True,
        diff=True,
        extra={
            "root_path": root,
            "tree_id": "tree-1",
            "ops": [
                {
                    "selector": {"kind": "node_id", "node_id": NODE_UUID},
                    "new_code": "b = 2\n",
                }
            ],
        },
    )
    with patch(
        "ai_editor.commands.compose_cst_ops_flow.get_tree", return_value=tree
    ):
        out = PythonFileHandler().replace(req)
    assert out.success is True
    assert f.read_text(encoding="utf-8") == "a = 1\n"
    assert out.data.get("preview_only") is True
    assert out.data.get("diff")


def test_invalid_node_id_selector_fails_before_backup_and_db(tmp_path: Path) -> None:
    root, f = _root_with_file(tmp_path, "m.py", "a = 1\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="m.py",
        handler_id="python",
        operation="replace",
        dry_run=False,
        backup=True,
        extra={
            "root_path": root,
            "ops": [
                {
                    "selector": {"kind": "node_id", "node_id": "not-a-uuid"},
                    "new_code": "x",
                }
            ],
        },
    )
    with (
        patch(
            "ai_editor.commands.compose_cst_ops_flow.BackupManager",
        ) as bm_cls,
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            MagicMock(),
        ) as open_db,
    ):
        out = PythonFileHandler().replace(req)
    assert out.success is False
    assert out.code == "INVALID_OPS"
    bm_cls.assert_not_called()
    open_db.assert_not_called()
    assert f.read_bytes() == b"a = 1\n"


def test_parse_validation_failure_before_apply_skips_backup_and_db(
    tmp_path: Path,
) -> None:
    """``validate_and_write_temp`` runs before ``BackupManager`` / DB open on apply."""
    root, f = _root_with_file(tmp_path, "ok.py", "a = 1\n")
    fake_temp = tmp_path / "fake_cst_temp.py"
    fake_temp.write_text("a = 2\n", encoding="utf-8")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="ok.py",
        handler_id="python",
        operation="replace",
        dry_run=False,
        backup=True,
        extra={
            "root_path": root,
            "ops": [
                {
                    "selector": {"kind": "range", "start_line": 1, "end_line": 1},
                    "new_code": "a = 2\n",
                }
            ],
        },
    )
    val_err = ErrorResult(
        message="Validation failed: compile: bad",
        code="VALIDATION_ERROR",  # type: ignore[arg-type]
        details={},
    )
    with (
        patch(
            "ai_editor.commands.compose_cst_ops_flow.validate_and_write_temp",
            return_value=(fake_temp, val_err, None),
        ),
        patch(
            "ai_editor.commands.compose_cst_ops_flow.BackupManager",
        ) as bm_cls,
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            MagicMock(),
        ) as open_db,
    ):
        out = PythonFileHandler().replace(req)
    assert out.success is False
    assert out.code == "VALIDATION_ERROR"
    bm_cls.assert_not_called()
    open_db.assert_not_called()
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_python_read_lines_syntax_broken_file(tmp_path: Path) -> None:
    root, f = _root_with_file(tmp_path, "bad.py", "this is not valid python !!!\n")
    req = FileHandlerRequest(
        project_id="p1",
        file_path="bad.py",
        handler_id="python",
        operation="read",
        extra={"absolute_path": f, "start_line": 1, "end_line": 1},
    )
    out = PythonFileHandler().read(req)
    assert out.success is True
    assert out.data.get("lines") == ["this is not valid python !!!"]


def test_python_read_cst_view_requires_tree_id() -> None:
    req = FileHandlerRequest(
        project_id="p1",
        file_path="x.py",
        handler_id="python",
        operation="read",
        extra={"absolute_path": Path("/tmp/x.py"), "view_mode": "cst"},
    )
    out = PythonFileHandler().read(req)
    assert out.success is False
    assert "tree_id" in out.message.lower()


def test_python_handler_registration_ready() -> None:
    h = PythonFileHandler()
    assert h.handler_id == "python"
    assert h.ready_for_all_operations_schema()
