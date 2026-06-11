"""
Utilities for CST module patching tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional

import libcst as cst


def _is_module_docstring(stmt: cst.BaseStatement) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    if len(stmt.body) != 1:
        return False
    expr = stmt.body[0]
    if not isinstance(expr, cst.Expr):
        return False
    return isinstance(expr.value, cst.SimpleString)


def move_module_imports_to_top(module: cst.Module) -> cst.Module:
    """
    Move all *module-level* imports to the top of the module body.

    This does not touch imports inside functions/classes (lazy imports).
    Preserves relative order of imports as they appear in the file.
    """
    if not module.body:
        return module

    body = list(module.body)
    docstring_stmt: Optional[cst.BaseStatement] = None
    rest = body
    if _is_module_docstring(body[0]):
        docstring_stmt = body[0]
        rest = body[1:]

    imports: list[cst.BaseStatement] = []
    new_rest: list[cst.BaseStatement] = []
    for stmt in rest:
        if isinstance(stmt, (cst.Import, cst.ImportFrom)):
            imports.append(stmt)
        else:
            new_rest.append(stmt)

    new_body: list[cst.BaseStatement] = []
    if docstring_stmt is not None:
        new_body.append(docstring_stmt)
    new_body.extend(imports)
    new_body.extend(new_rest)
    return module.with_changes(body=new_body)


def compile_module(source: str, filename: str = "<cst_module>") -> tuple[bool, str]:
    """
    "Compile" module source to validate syntax.

    Returns:
        (ok, error_message)
    """
    try:
        compile(source, filename, "exec")
        return True, ""
    except Exception as e:
        return False, str(e)


def unified_diff(old: str, new: str, path: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{path} (before)",
        tofile=f"{path} (after)",
    )
    return "".join(diff)


def write_with_backup(
    target_file: Path, new_source: str, create_backup: bool = True
) -> Optional[Path]:
    if create_backup and target_file.exists():
        backup_dir = target_file.parent / ".code_mapper_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{target_file.name}.backup"
        backup_path.write_text(
            target_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        backup_path = None

    target_file.write_text(new_source, encoding="utf-8")
    return backup_path
