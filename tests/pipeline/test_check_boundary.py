"""Adversarial contract tests for pipeline/checks/check_boundary.py (C-001).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

These tests never monkeypatch the check's internals and never assert against
a hand-built fake file list. Every test that needs a violation copies the
real ``src/tree_engine`` source tree into a pytest ``tmp_path`` and injects
the violation into that copy, then runs the real, unmodified
``check_boundary()`` (or the real CLI, out of process) against it. This
proves the check catches violations mechanically via ``ast`` parsing, not
because a test told it what to find.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.checks.check_boundary import (
    CHECK_DESCRIPTION,
    CHECK_NAME,
    TREE_ENGINE_RELATIVE,
    check_boundary,
)
from pipeline.registry import CheckResult, CheckStatus, get_registry

# tests/pipeline/test_check_boundary.py -> tests/pipeline -> tests -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_TREE_ENGINE = REPO_ROOT / TREE_ENGINE_RELATIVE


def _copy_tree_engine(dest_repo_root: Path) -> Path:
    """Copy the real src/tree_engine tree verbatim into dest_repo_root."""
    dest = dest_repo_root / "src" / "tree_engine"
    shutil.copytree(
        REAL_TREE_ENGINE,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return dest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_cli(args: list, cwd: Path, pythonpath: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.cli", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def cloned_repo(tmp_path: Path) -> Path:
    """A tmp_path root holding a verbatim copy of the real src/tree_engine tree.

    Never the real repository: every injection in this file happens under
    this per-test tmp_path copy, so the real checkout is never mutated.
    """
    _copy_tree_engine(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# Baseline: the real repository and a clean clone both pass right now.
# --------------------------------------------------------------------------


def test_real_repository_passes_right_now() -> None:
    """Against the real, unmodified repository the check returns PASS."""
    result = check_boundary()
    assert isinstance(result, CheckResult)
    assert result.status is CheckStatus.PASS, result.output


def test_clean_copied_tree_passes(cloned_repo: Path) -> None:
    """A verbatim, unmodified clone of the real tree also passes."""
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


def test_result_is_deterministic_across_repeated_runs(cloned_repo: Path) -> None:
    first = check_boundary(repo_root=cloned_repo)
    second = check_boundary(repo_root=cloned_repo)
    assert first.status == second.status
    assert first.message == second.message
    assert first.output == second.output


# --------------------------------------------------------------------------
# Catches forbidden imports in every syntactic disguise.
# --------------------------------------------------------------------------


def test_plain_import_in_core_detected(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_plain.py"
    _write(probe, "import libcst\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_plain.py" in result.output
    assert "libcst" in result.output


def test_aliased_import_detected(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_alias.py"
    _write(probe, "import libcst as _lc\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_alias.py" in result.output
    assert "libcst" in result.output


def test_from_import_aliased_detected(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_from_alias.py"
    _write(probe, "from tree_sitter import Language as _L\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_from_alias.py" in result.output
    assert "tree_sitter" in result.output


def test_dotted_legacy_import_aliased_detected(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_dotted.py"
    _write(probe, "import ai_editor.cst_query.parser as _pp\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_dotted.py" in result.output
    assert "ai_editor" in result.output


def test_lazy_import_inside_function_detected(cloned_repo: Path) -> None:
    """A lazy, function-body import must be caught, not just module-level ones."""
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_lazy.py"
    _write(probe, "def do_something():\n    import libcst\n    return libcst\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_lazy.py" in result.output
    assert "libcst" in result.output


def test_violation_output_includes_file_line_import_and_category(cloned_repo: Path) -> None:
    """Every reported violation carries file, line, import name, and rule category."""
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_detail.py"
    _write(probe, "\n\nimport libcst\n")  # the import lands on line 3
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_detail.py:3" in result.output
    assert "libcst" in result.output
    assert "parser-library-outside-plugins" in result.output


# --------------------------------------------------------------------------
# Never false-positives on mere text mentioning a forbidden name.
# --------------------------------------------------------------------------


def test_comment_mention_not_flagged(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_comment.py"
    _write(probe, "# import libcst -- reminder only, not a real import\nVALUE = 1\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


def test_docstring_mention_not_flagged(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_docstring.py"
    _write(probe, '"""This module discusses import libcst in prose only."""\nVALUE = 1\n')
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


def test_string_literal_mention_not_flagged(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/core/_boundary_probe_string.py"
    _write(probe, 'NOTE = "import libcst"\n')
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


# --------------------------------------------------------------------------
# Never false-positives on the legitimate plugin imports.
# --------------------------------------------------------------------------


def test_python_plugin_libcst_import_is_exempt(cloned_repo: Path) -> None:
    plugin_file = cloned_repo / "src/tree_engine/plugins/python/plugin.py"
    assert plugin_file.is_file()
    source = plugin_file.read_text(encoding="utf-8")
    assert "libcst" in source  # sanity: the real plugin genuinely imports libcst
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


def test_bsl_plugin_tree_sitter_import_is_exempt(cloned_repo: Path) -> None:
    plugin_file = cloned_repo / "src/tree_engine/plugins/bsl/plugin.py"
    assert plugin_file.is_file()
    source = plugin_file.read_text(encoding="utf-8")
    assert "tree_sitter" in source  # sanity: the real plugin genuinely imports it
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


# --------------------------------------------------------------------------
# Rule scope: legacy-package self-containment applies everywhere, parser
# exemption applies only to plugins/, and code outside the package is not
# scanned at all.
# --------------------------------------------------------------------------


def test_forbidden_legacy_import_in_storage_detected(cloned_repo: Path) -> None:
    probe = cloned_repo / "src/tree_engine/storage/_boundary_probe_storage.py"
    _write(probe, "import mcp_proxy\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_storage.py" in result.output
    assert "mcp_proxy" in result.output


def test_legacy_import_inside_plugins_still_flagged(cloned_repo: Path) -> None:
    """The plugins/ exemption covers parser libraries only, not legacy imports."""
    probe = cloned_repo / "src/tree_engine/plugins/python/_boundary_probe_plugin_legacy.py"
    _write(probe, "import code_analysis_server\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "_boundary_probe_plugin_legacy.py" in result.output
    assert "code_analysis_server" in result.output


def test_multiple_violations_reported_together(cloned_repo: Path) -> None:
    core_probe = cloned_repo / "src/tree_engine/core/_boundary_probe_multi_core.py"
    storage_probe = cloned_repo / "src/tree_engine/storage/_boundary_probe_multi_storage.py"
    _write(core_probe, "import libcst\n")
    _write(storage_probe, "import ai_editor\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.FAIL
    assert "2 PackageBoundary violation" in result.message
    assert "_boundary_probe_multi_core.py" in result.output
    assert "_boundary_probe_multi_storage.py" in result.output


def test_adapter_module_outside_tree_engine_is_not_scanned(cloned_repo: Path) -> None:
    """An integration adapter living outside src/tree_engine is never scanned."""
    adapter_file = cloned_repo / "adapter" / "ai_editor_bridge.py"
    _write(adapter_file, "import ai_editor\nimport mcp_proxy\n")
    result = check_boundary(repo_root=cloned_repo)
    assert result.status is CheckStatus.PASS, result.output


# --------------------------------------------------------------------------
# Result shape: a real CheckResult/CheckStatus, never a bare bool or string.
# --------------------------------------------------------------------------


def test_check_boundary_returns_checkresult_with_status_enum(cloned_repo: Path) -> None:
    result = check_boundary(repo_root=cloned_repo)
    assert isinstance(result, CheckResult)
    assert isinstance(result.status, CheckStatus)
    assert result.status in (CheckStatus.PASS, CheckStatus.FAIL)
    assert not isinstance(result, bool)
    assert not isinstance(result, str)


# --------------------------------------------------------------------------
# Registry + CLI wiring: the check is discoverable and runnable end to end.
# --------------------------------------------------------------------------


def test_check_boundary_is_registered_on_shared_registry() -> None:
    registry = get_registry()
    assert CHECK_NAME in registry
    entry = registry.lookup_by_name(CHECK_NAME)
    assert entry.name == CHECK_NAME
    assert entry.description == CHECK_DESCRIPTION
    assert entry.func is check_boundary


def test_cli_check_boundary_subcommand_exits_zero_on_real_repo() -> None:
    proc = _run_cli(["check-boundary-check"], cwd=REPO_ROOT, pythonpath=REPO_ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"[PASS] {CHECK_NAME}" in proc.stdout


def test_cli_list_subcommand_includes_check_boundary() -> None:
    proc = _run_cli(["list"], cwd=REPO_ROOT, pythonpath=REPO_ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert CHECK_NAME in proc.stdout


def test_cli_check_boundary_subcommand_exits_one_on_violation(tmp_path: Path) -> None:
    """Full black-box run: a real subprocess, a real copied repo, a real violation."""
    dest_root = tmp_path / "repo_copy"
    shutil.copytree(
        REPO_ROOT / "pipeline",
        dest_root / "pipeline",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _copy_tree_engine(dest_root)
    probe = dest_root / "src/tree_engine/core/_boundary_probe_cli.py"
    _write(probe, "import libcst\n")

    proc = _run_cli(["check-boundary-check"], cwd=dest_root, pythonpath=dest_root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"[FAIL] {CHECK_NAME}" in proc.stdout
    assert "_boundary_probe_cli.py" in proc.stdout
