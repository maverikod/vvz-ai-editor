"""Unit tests for universal_file_edit command helpers."""

from __future__ import annotations

import asyncio

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.cst_modify_tree_ops_build import build_tree_operations
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
    _normalized_cst_modify_operation,
    _resolve_stable_to_span,
)
from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from ai_editor.core.cst_tree.tree_builder import (
    get_tree,
    load_file_to_tree,
    remove_tree,
)
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_sidecar import write_sidecar_atomic
from ai_editor.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from tests.thin_editor_ca_mocks import (
    edit_guard_context,
    open_ca_file,
    upstream_context,
)


def test_normalized_cst_modify_operation_maps_type_to_action() -> None:
    op = {"type": "replace", "node_id": "00000000-0000-4000-8000-000000000001"}
    normalized = _normalized_cst_modify_operation(op)
    assert normalized["action"] == "replace"
    assert normalized["type"] == "replace"


def test_validate_replace_snippet_via_module_accepts_assignment() -> None:
    op = {
        "type": "replace",
        "node_id": "00000000-0000-4000-8000-000000000001",
        "code_lines": ["DEFAULT_TIMEOUT = 60"],
    }
    normalized = _normalized_cst_modify_operation(op)
    assert "DEFAULT_TIMEOUT = 60" in normalized.get("code", "")
    assert "code_lines" not in normalized


def test_validate_replace_snippet_via_module_dedents_indented_code_lines() -> None:
    op = {
        "type": "replace",
        "node_id": "00000000-0000-4000-8000-000000000001",
        "code_lines": [
            "            abs_path.write_text('x', encoding='utf-8')\n",
        ],
    }
    normalized = _normalized_cst_modify_operation(op)
    assert "abs_path.write_text('x', encoding='utf-8')" in normalized.get("code", "")


def test_validate_replace_snippet_via_module_no_double_newlines() -> None:
    op = {
        "type": "replace",
        "node_id": "00000000-0000-4000-8000-000000000001",
        "code_lines": [
            "def foo() -> str:\n",
            '    return "bar"\n',
        ],
    }
    normalized = _normalized_cst_modify_operation(op)
    code = normalized.get("code", "")
    assert "def foo() -> str:\n    return" in code
    assert "def foo() -> str:\n\n    return" not in code


def test_validate_replace_snippet_rejects_compound_clause_header() -> None:
    op = {
        "type": "replace",
        "node_id": "00000000-0000-4000-8000-000000000001",
        "code_lines": ["elif suffix == '.yaml':\n", "    pass\n"],
    }
    with pytest.raises(ValueError, match="compound clause header"):
        _normalized_cst_modify_operation(op)


def test_replace_simple_statement_in_nested_elif_branch(tmp_path) -> None:
    path = tmp_path / "nested_elif.py"
    path.write_text(
        "def create():\n"
        "    if True:\n"
        "        first()\n"
        "    elif suffix == '.yaml':\n"
        "        write_yaml()\n"
        "    else:\n"
        "        write_other()\n",
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(path))
    try:
        target = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "SimpleStatementLine" and m.start_line == 5
        )
        op = _normalized_cst_modify_operation(
            {
                "type": "replace",
                "node_id": target.node_id,
                "code_lines": ["        write_yaml_fixed()\n"],
            }
        )
        built, err = build_tree_operations(tree, [op])
        assert err is None and built
        tree = modify_tree(tree.tree_id, built)
        assert "write_yaml_fixed()" in tree.module.code
        assert "write_yaml()" not in tree.module.code
    finally:
        remove_tree(tree.tree_id)


def test_replace_stable_id_in_elif_body_matches_preview_line(tmp_path) -> None:
    """stable_id from preview must replace the elif-body line, not the prior sibling."""
    path = tmp_path / "open_like.py"
    path.write_text(
        "def execute(self):\n"
        "    if not abs_path.exists():\n"
        "        abs_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        suffix = abs_path.suffix.lower()\n"
        "        if suffix == '.py':\n"
        "            abs_path.write_text('py', encoding='utf-8')\n"
        "        elif suffix in ('.yaml', '.yml'):\n"
        '            abs_path.write_text("{}", encoding="utf-8")\n'
        "        else:\n"
        '            abs_path.write_text("", encoding="utf-8")\n',
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(path))
    try:
        yaml_stmt = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "SimpleStatementLine" and m.start_line == 8 and m.stable_id
        )
        op = _normalized_cst_modify_operation(
            {
                "type": "replace",
                "node_id": yaml_stmt.stable_id,
                "code_lines": [
                    '            abs_path.write_text("YAML_FIXED", encoding="utf-8")\n',
                ],
            }
        )
        resolved = _resolve_stable_to_span(op, tree)
        built, err = build_tree_operations(tree, [resolved])
        assert err is None and built
        tree = modify_tree(tree.tree_id, built)
        assert "YAML_FIXED" in tree.module.code
        assert 'write_text("{}", encoding="utf-8")' not in tree.module.code
        assert "suffix = abs_path.suffix.lower()" in tree.module.code
        logical_lines = [
            line
            for line in tree.module.code.splitlines()
            if not line.strip().startswith("# @node-id:")
        ]
        yaml_logical_line = next(
            i + 1 for i, line in enumerate(logical_lines) if "YAML_FIXED" in line
        )
        suffix_logical_line = next(
            i + 1
            for i, line in enumerate(logical_lines)
            if "suffix = abs_path.suffix.lower()" in line
        )
        assert yaml_logical_line == 8
        assert suffix_logical_line < yaml_logical_line
    finally:
        remove_tree(tree.tree_id)


def test_replace_simple_statement_in_for_and_try_bodies(tmp_path) -> None:
    for_loop_source = (
        "def run():\n" "    for item in items:\n" "        process(item)\n"
    )
    try_source = (
        "def run():\n"
        "    try:\n"
        "        risky()\n"
        "    except ValueError:\n"
        "        handle()\n"
    )
    for source, line_no, replacement, needle in (
        (for_loop_source, 3, "process_fast(item)", "process_fast(item)"),
        (try_source, 5, "handle_value_error()", "handle_value_error()"),
    ):
        path = tmp_path / f"nested_{line_no}.py"
        path.write_text(source, encoding="utf-8")
        tree = load_file_to_tree(str(path))
        try:
            target = next(
                m
                for m in tree.metadata_map.values()
                if m.type == "SimpleStatementLine" and m.start_line == line_no
            )
            op = _normalized_cst_modify_operation(
                {
                    "type": "replace",
                    "node_id": target.node_id,
                    "code_lines": [f"        {replacement}\n"],
                }
            )
            built, err = build_tree_operations(tree, [op])
            assert err is None and built
            tree = modify_tree(tree.tree_id, built)
            assert needle in tree.module.code
        finally:
            remove_tree(tree.tree_id)


def test_normalized_cst_modify_operation_prefers_explicit_action() -> None:
    op = {"type": "insert", "action": "delete", "node_id": "x"}
    normalized = _normalized_cst_modify_operation(op)
    assert normalized["action"] == "delete"


def test_universal_file_write_command_inherits_base_mcp_command() -> None:
    assert issubclass(UniversalFileWriteCommand, BaseMCPCommand)
    assert hasattr(UniversalFileWriteCommand, "run")
    assert UniversalFileWriteCommand.name == "universal_file_write"


def test_normalized_cst_modify_operation_leaves_op_without_type_unchanged() -> None:
    op = {"node_id": "00000000-0000-4000-8000-000000000001"}
    normalized = _normalized_cst_modify_operation(op)
    assert "action" not in normalized


def test_resolve_stable_to_span_allows_second_edit_after_tree_rebuild(
    tmp_path,
) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        "def foo():\n    return 1\n",
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(path))
    try:
        func_meta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "foo"
        )
        stable_id = func_meta.stable_id
        op = {
            "type": "replace",
            "node_id": stable_id,
            "code_lines": ["def foo():\n", "    return 2\n"],
        }
        resolved = _resolve_stable_to_span(op, tree)
        built, err = build_tree_operations(
            tree, [_normalized_cst_modify_operation(resolved)]
        )
        assert err is None and built
        tree = modify_tree(tree.tree_id, built)
        write_sidecar_atomic(path, tree)

        resolved2 = _resolve_stable_to_span(op, tree)
        built2, err2 = build_tree_operations(
            tree, [_normalized_cst_modify_operation(resolved2)]
        )
        assert err2 is None and built2
        assert resolved2["node_id"] in tree.metadata_map
        assert resolved2["node_id"] != stable_id or stable_id in tree.metadata_map
    finally:
        remove_tree(tree.tree_id)


@pytest.mark.asyncio
async def test_failed_insert_rolls_back_in_memory_tree(tmp_path) -> None:
    """Invalid insert must not leave a mutated in-memory tree (BUG-004)."""
    path = tmp_path / "future_first.py"
    path.write_text(
        "from __future__ import annotations\n\nx = 1\n",
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(path))
    original_code = tree.module.code
    descriptor = resolve_format_group(path)
    session = create_session(
        path,
        descriptor,
        file_path=path.name,
        tree_id=tree.tree_id,
        ca_session_id="test-ca-1",
    )
    try:
        cmd = UniversalFileEditCommand()
        with edit_guard_context():
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "insert",
                        "parent_node_id": "__root__",
                        "position": "first",
                        "code_lines": ["import sys"],
                    }
                ],
            )
        assert isinstance(result, ErrorResult)
        restored = get_tree(tree.tree_id)
        assert restored is not None
        assert restored.module.code == original_code
        assert "import sys" not in restored.module.code
    finally:
        release_session(session.session_id)
        remove_tree(tree.tree_id)


_CLASS_TWO_METHODS = """
class Foo:
    def method_a(self) -> int:
        return 1

    def method_b(self) -> str:
        return "original"
"""


def _function_stable_ids_by_name(
    tree_id: str, names: tuple[str, ...]
) -> dict[str, str]:
    tree = get_tree(tree_id)
    assert tree is not None
    root_id = tree.root_node_id
    found: dict[str, str] = {}
    for meta in tree.metadata_map.values():
        if (
            meta.type == "FunctionDef"
            and meta.name in names
            and meta.parent_id != root_id
        ):
            found[meta.name] = meta.stable_id
    assert set(found) == set(names)
    return found


_DOG_CLASSMETHOD = """
class Dog:
    @classmethod
    def from_dict(cls, data: dict) -> 'Dog':
        return cls(data['name'])
"""


@pytest.mark.asyncio
async def test_universal_file_edit_preserves_decorator_stable_id(tmp_path) -> None:
    """Replace method body without @ lines must keep decorator stable_id (BUG-008b)."""
    path = tmp_path / "dog.py"
    path.write_text(_DOG_CLASSMETHOD.strip(), encoding="utf-8")
    tree = load_file_to_tree(str(path))
    dec_stable = fn_stable = None
    for m in tree.metadata_map.values():
        if m.type == "Decorator":
            dec_stable = m.stable_id
        if m.type == "FunctionDef" and m.name == "from_dict":
            fn_stable = m.stable_id
    assert dec_stable and fn_stable
    descriptor = resolve_format_group(path)
    session = create_session(
        path,
        descriptor,
        file_path=path.name,
        tree_id=tree.tree_id,
        ca_session_id="test-ca-1",
    )
    try:
        cmd = UniversalFileEditCommand()
        with edit_guard_context():
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "replace",
                        "node_id": fn_stable,
                        "code_lines": [
                            "def from_dict(cls, data: dict) -> 'Dog':",
                            '    """Create from dict."""',
                            "    return cls(**data)",
                        ],
                    },
                ],
            )
        assert isinstance(result, SuccessResult)
        updated = get_tree(session.tree_id)
        assert updated is not None
        dec_after = None
        for m in updated.metadata_map.values():
            if m.type == "Decorator":
                dec_after = m.stable_id
        assert dec_after == dec_stable
        assert "@classmethod" in updated.module.code
    finally:
        release_session(session.session_id)
        remove_tree(tree.tree_id)


@pytest.mark.asyncio
async def test_batch_two_independent_replaces(tmp_path) -> None:
    """Two sequential replaces must both apply (refresh node_ref between edits)."""
    path = tmp_path / "cls.py"
    path.write_text(_CLASS_TWO_METHODS.strip(), encoding="utf-8")
    tree = load_file_to_tree(str(path))
    stable_ids = _function_stable_ids_by_name(tree.tree_id, ("method_a", "method_b"))
    descriptor = resolve_format_group(path)
    session = create_session(
        path,
        descriptor,
        file_path=path.name,
        tree_id=tree.tree_id,
        ca_session_id="test-ca-1",
    )
    try:
        cmd = UniversalFileEditCommand()
        with edit_guard_context():
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "replace",
                        "node_id": stable_ids["method_a"],
                        "code_lines": [
                            "def method_a(self) -> int:",
                            "    return 1",
                        ],
                    },
                ],
            )
        assert isinstance(result, SuccessResult)
        updated = get_tree(session.tree_id)
        assert updated is not None
        method_b_stable = next(
            m.stable_id
            for m in updated.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "method_b"
        )
        with edit_guard_context():
            result2 = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "replace",
                        "node_id": method_b_stable,
                        "code_lines": [
                            "def method_b(self) -> str:",
                            "    return 'updated'",
                        ],
                    },
                ],
            )
        assert isinstance(result2, SuccessResult)
        assert result2.data.get("success") is True
        assert result2.data.get("updated") is True
        assert session.tree_id is not None
        final = get_tree(session.tree_id)
        assert final is not None
        code = final.module.code
        assert "return 'updated'" in code
        assert 'return "original"' not in code
    finally:
        release_session(session.session_id)
        remove_tree(tree.tree_id)


_SANDBOX_MODULE = '''"""Sandbox test module."""

from __future__ import annotations


DEFAULT_TIMEOUT = 30


def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"
'''


@pytest.mark.asyncio
async def test_edit_replace_via_annotated_text_node_ref(tmp_path) -> None:
    """node_ref from annotated full-text must replace SimpleStatementLine (SUB-1)."""
    import re

    from ai_editor.commands.universal_file_preview_command import (
        UniversalFilePreviewCommand,
    )

    project_id = "00000000-0000-0000-0000-000000000002"
    rel = "sandbox_test.py"
    sid, workspace, origin, upstream = await open_ca_file(
        tmp_path,
        project_id=project_id,
        file_path=rel,
        content=_SANDBOX_MODULE.encode("utf-8"),
    )

    prev = UniversalFilePreviewCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        preview_res = await prev.execute(
            **prev.validate_params(
                {
                    "project_id": project_id,
                    "file_path": rel,
                    "session_id": sid,
                }
            )
        )
    assert isinstance(preview_res, SuccessResult)
    focus_text = preview_res.data["focus"].get("text") or ""
    focus_line = next(
        line for line in focus_text.splitlines() if "DEFAULT_TIMEOUT" in line
    )
    preview_short_id = int(re.match(r"\[(\d+)\]", focus_line).group(1))

    cmd = UniversalFileEditCommand()
    wr = UniversalFileWriteCommand()
    with upstream_context(workspace=workspace, upstream=upstream):
        edit_res = await cmd.execute(
            project_id=project_id,
            session_id=sid,
            operations=[
                {
                    "type": "replace",
                    "node_ref": preview_short_id,
                    "code_lines": ["DEFAULT_TIMEOUT = 60\n"],
                }
            ],
        )
        assert isinstance(edit_res, SuccessResult)
        write_preview = await wr.execute(
            project_id=project_id,
            session_id=sid,
            write_mode="preview",
        )
        assert isinstance(write_preview, SuccessResult)
        assert write_preview.data.get("phase") == "preview"
        assert write_preview.data.get("has_changes") is True
        commit = await wr.execute(
            project_id=project_id,
            session_id=sid,
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert commit.data.get("uploaded") is True
    assert "DEFAULT_TIMEOUT = 60" in origin.read_text(encoding="utf-8")

    release_session(sid)
