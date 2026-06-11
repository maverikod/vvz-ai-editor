"""Tests for ai_editor.core.file_identity."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from ai_editor.core.file_identity import (
    FileIdentityCase,
    classify_file_identity_case,
    is_same_absolute_file,
    normalize_project_file_path,
    relative_path_for_project,
)


def test_normalize_project_file_path_same_file_different_syntax(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    f.write_text("x\n", encoding="utf-8")
    direct = normalize_project_file_path(f)
    via_parent = normalize_project_file_path(tmp_path / ".." / tmp_path.name / "f.py")
    assert direct == via_parent
    assert is_same_absolute_file(f, tmp_path / ".." / tmp_path.name / "f.py")


def test_is_same_absolute_file_equivalence(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    a.write_text("1", encoding="utf-8")
    assert is_same_absolute_file(str(a.resolve()), a.resolve())
    assert is_same_absolute_file(a, str(a))


def test_relative_path_for_project_posix_under_root(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    sub = root / "pkg" / "m.py"
    sub.parent.mkdir(parents=True)
    sub.write_text("pass\n", encoding="utf-8")
    rel = relative_path_for_project(sub.resolve(), root.resolve())
    assert rel == "pkg/m.py"


def test_relative_path_for_project_outside_root_raises(tmp_path: Path) -> None:
    root = tmp_path / "inside"
    root.mkdir()
    outsider = tmp_path / "outside" / "x.py"
    outsider.parent.mkdir(parents=True)
    outsider.write_text("y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not within project root"):
        relative_path_for_project(outsider.resolve(), root.resolve())


def test_classify_different_project_same_relative_only(tmp_path: Path) -> None:
    root_a = tmp_path / "pa"
    root_b = tmp_path / "pb"
    root_a.mkdir()
    root_b.mkdir()
    fa = root_a / "lib" / "x.py"
    fb = root_b / "lib" / "x.py"
    fa.parent.mkdir(parents=True)
    fb.parent.mkdir(parents=True)
    fa.write_text("1", encoding="utf-8")
    fb.write_text("2", encoding="utf-8")
    rel = "lib/x.py"
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    case = classify_file_identity_case(
        project_id_a=pid_a,
        absolute_path_a=fa.resolve(),
        relative_path_a=rel,
        project_id_b=pid_b,
        absolute_path_b=fb.resolve(),
        relative_path_b=rel,
    )
    assert case is FileIdentityCase.DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY


def test_classify_nested_roots_same_absolute_different_projects(tmp_path: Path) -> None:
    outer = tmp_path / "nest" / "super"
    inner = outer / "submodule"
    inner.mkdir(parents=True)
    f = inner / "x.py"
    f.write_text("# x\n", encoding="utf-8")
    p = f.resolve()
    pid_outer = str(uuid.uuid4())
    pid_inner = str(uuid.uuid4())
    rel_outer = relative_path_for_project(p, outer.resolve())
    rel_inner = relative_path_for_project(p, inner.resolve())
    case = classify_file_identity_case(
        project_id_a=pid_outer,
        absolute_path_a=p,
        relative_path_a=rel_outer,
        project_id_b=pid_inner,
        absolute_path_b=p,
        relative_path_b=rel_inner,
    )
    assert case is FileIdentityCase.DIFFERENT_PROJECT_SAME_ABSOLUTE_PATH


def test_classify_same_project_same_absolute(tmp_path: Path) -> None:
    root = tmp_path / "one"
    root.mkdir()
    f = root / "a.py"
    f.write_text("z\n", encoding="utf-8")
    pid = str(uuid.uuid4())
    rel = relative_path_for_project(f.resolve(), root.resolve())
    case = classify_file_identity_case(
        project_id_a=pid,
        absolute_path_a=f.resolve(),
        relative_path_a=rel,
        project_id_b=pid,
        absolute_path_b=f.resolve(),
        relative_path_b=rel,
    )
    assert case is FileIdentityCase.SAME_PROJECT_SAME_ABSOLUTE_PATH


def test_classify_unrelated_different_projects(tmp_path: Path) -> None:
    ra = tmp_path / "r1"
    rb = tmp_path / "r2"
    ra.mkdir()
    rb.mkdir()
    fa = ra / "a.py"
    fb = rb / "b.py"
    fa.write_text("1", encoding="utf-8")
    fb.write_text("2", encoding="utf-8")
    case = classify_file_identity_case(
        project_id_a=str(uuid.uuid4()),
        absolute_path_a=fa.resolve(),
        relative_path_a="a.py",
        project_id_b=str(uuid.uuid4()),
        absolute_path_b=fb.resolve(),
        relative_path_b="b.py",
    )
    assert case is FileIdentityCase.UNRELATED
