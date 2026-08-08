"""Tests for the canonical pipeline CLI (``pipeline/cli.py``) and its use of
``pipeline/registry.py`` (C-022, {p110}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Two strategies, kept apart:

* In-process unit tests build a fresh, private ``Registry()`` and call
  ``pipeline.cli`` functions directly. Passing an explicit registry makes
  ``main()`` skip real filesystem discovery (its ``using_default_registry``
  guard), so these tests never touch the process-wide singleton and need no
  save/restore.
* Subprocess tests invoke the real ``python -m pipeline.cli`` against the
  real repository or a throwaway copy of ``pipeline/`` under ``tmp_path``,
  proving actual discovery, resilience, and PYTHONPATH behavior. A fresh
  interpreter process is the only honest way to test module discovery.

PYTHONPATH reality pinned by
``test_check_recovery_resolves_tree_engine_from_the_installed_distribution``:
``pipeline.checks.check_recovery`` imports ``tree_engine`` at module scope,
and since the engine became its own distribution (``ai-editor-tree-engine``)
that import is satisfied from site-packages, so ``PYTHONPATH=.`` is enough
and ``src`` is no longer load-bearing. No test writes into the real
``pipeline/checks/`` directory; discovery and resilience scenarios copy
``pipeline/`` into ``tmp_path`` first.
"""

from __future__ import annotations

import io
import os
import subprocess
import shutil
import sys
from pathlib import Path
from typing import List

import pytest

from pipeline import cli
from pipeline.registry import Check, CheckResult, CheckStatus, Registry

# Shared helpers / fixtures

def _repo_root() -> Path:
    """Repository root: three levels above this file (tests/pipeline/x.py)."""
    return Path(__file__).resolve().parents[2]

def _run_cli(args: List[str], cwd: Path, pythonpath: str) -> subprocess.CompletedProcess:
    """Invoke the real ``python -m pipeline.cli`` as a subprocess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = pythonpath
    return subprocess.run(
        [sys.executable, "-m", "pipeline.cli", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        # The no-argument aggregate runs the WHOLE real battery: seven checks,
        # measured at 57 s today (check-roundtrip alone samples ~1000 real files).
        # 60 s was the binding constraint and made this flaky as checks landed;
        # this cap is for a hang, not for a slow-but-working run.
        timeout=300,
    )

@pytest.fixture()
def pipeline_copy(tmp_path: Path) -> Path:
    """Throwaway copy of real ``pipeline/`` under tmp_path; add/remove/break
    check modules here only -- the real ``pipeline/checks/`` stays untouched."""
    dest = tmp_path / "pipeline"
    shutil.copytree(_repo_root() / "pipeline", dest)
    return tmp_path

def _real_pythonpath(extra: Path) -> str:
    return f"{extra}:{_repo_root() / 'src'}"

def _ok(msg: str = "") -> CheckResult:
    return CheckResult.ok(msg)

def _fail(msg: str = "") -> CheckResult:
    return CheckResult.fail(msg)

# In-process unit tests: main()/run_all()/run_named_check()/list with an
# isolated Registry() -- the process-wide singleton is never touched.

def test_no_argument_runs_all_checks_aggregate_exit():
    # Text assertions call run_all() directly with an explicit stream= (see
    # test_default_stream_argument_is_not_redirect_stdout_capturable for why).
    reg = Registry()
    reg.register("a", "check a", lambda: _ok("a passed"))
    reg.register("b", "check b", lambda: _fail("b broke"))
    buf = io.StringIO()
    assert cli.run_all(reg, stream=buf) == 1
    out = buf.getvalue()
    assert "[PASS] a - a passed" in out
    assert "[FAIL] b - b broke" in out
    assert "1/2 checks passed" in out
    assert cli.main([], registry=reg) == 1  # main() dispatches the same way

    reg2 = Registry()
    reg2.register("a", "check a", lambda: _ok())
    reg2.register("b", "check b", lambda: _ok())
    assert cli.run_all(reg2, stream=io.StringIO()) == 0
    assert cli.main([], registry=reg2) == 0

    assert cli.run_all(Registry(), stream=io.StringIO()) == 0  # empty passes

def test_single_check_invocation_by_name():
    calls = {"a": 0, "b": 0}

    def make(name, result):
        def _run():
            calls[name] += 1
            return result
        return _run

    reg = Registry()
    reg.register("a", "check a", make("a", _ok("a ran")))
    reg.register("b", "check b", make("b", _fail("b ran")))

    buf = io.StringIO()
    assert cli.run_named_check("a", registry=reg, stream=buf) == 0
    assert calls == {"a": 1, "b": 0}  # only the named check ran
    assert "[PASS] a - a ran" in buf.getvalue()
    assert cli.main(["a"], registry=reg) == 0  # main() dispatch parity

    assert cli.main(["b"], registry=reg) == 1
    assert calls == {"a": 2, "b": 1}

def test_list_mode_enumerates_without_executing():
    calls = {"a": 0, "b": 0}

    def make(name):
        def _run():
            calls[name] += 1
            return _ok()
        return _run

    reg = Registry()
    reg.register("b-check", "second registered", make("b"))
    reg.register("a-check", "first registered", make("a"))

    buf = io.StringIO()
    assert cli.list_registered_checks(reg, stream=buf) == 0
    assert calls == {"a": 0, "b": 0}  # nothing executed
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    # Registration order, not alphabetical: b-check was registered first.
    assert lines[0].startswith("b-check")
    assert "second registered" in lines[0]
    assert lines[1].startswith("a-check")
    assert "first registered" in lines[1]
    assert cli.main(["list"], registry=reg) == 0  # main() dispatch parity
    assert calls == {"a": 0, "b": 0}  # still nothing executed

    empty_buf = io.StringIO()
    assert cli.list_registered_checks(Registry(), stream=empty_buf) == 0
    assert "no checks registered" in empty_buf.getvalue()

def test_default_stream_argument_is_not_redirect_stdout_capturable():
    # Real quirk: the ``stream`` default binds to sys.stdout at cli.py's
    # import time, so contextlib.redirect_stdout can't intercept it later.
    import contextlib

    reg = Registry()
    reg.register("a", "d", lambda: _ok("x"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main([], registry=reg)
    assert buf.getvalue() == ""  # nothing arrives via the redirected object

    explicit = io.StringIO()
    cli.run_all(reg, stream=explicit)  # bypassing the default captures fine
    assert "[PASS] a - x" in explicit.getvalue()

def test_unknown_check_name_error(capsys):
    reg = Registry()
    reg.register("known", "the only one", lambda: _ok())
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["does-not-exist"], registry=reg)
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice: 'does-not-exist'" in err
    assert "known" in err

def test_registration_order_determinism():
    order: List[str] = []

    def make(name):
        def _run():
            order.append(name)
            return _ok()
        return _run

    reg = Registry()
    for name in ("third", "first", "second"):
        reg.register(name, name, make(name))
    # Registration order is call order here, not alphabetical.
    assert reg.names() == ["third", "first", "second"]
    assert [c.name for c in reg.list_checks()] == ["third", "first", "second"]

    cli.run_all(reg)
    assert order == ["third", "first", "second"]

def test_registry_not_found_error_path(capsys):
    empty = Registry()
    assert cli.run_named_check("anything", registry=empty) == 2
    err = capsys.readouterr().err
    assert "pipeline: error:" in err
    assert "the registry is empty" in err

    populated = Registry()
    populated.register("real-one", "d", lambda: _ok())
    assert cli.run_named_check("missing", registry=populated) == 2
    err2 = capsys.readouterr().err
    assert "known checks: real-one" in err2

# Registry's own guards -- exercised on a private Registry(), never on the
# process-wide singleton, so no save/restore is needed.

def test_registry_duplicate_registration_and_replace_true():
    reg = Registry()
    reg.register("dup", "first version", lambda: _ok("v1"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register("dup", "second version", lambda: _ok("v2"))
    # replace=True is the documented escape hatch.
    reg.register("dup", "second version", lambda: _ok("v2"), replace=True)
    assert reg.lookup_by_name("dup").description == "second version"
    assert reg.lookup_by_name("dup").run().message == "v2"

def test_registry_register_rejects_swapped_and_invalid_arguments():
    reg = Registry()
    # Swapped register(name, description, func): both TypeError guards fire.
    with pytest.raises(TypeError, match="description must be a string"):
        reg.register("x", lambda: _ok(), "not a description")
    with pytest.raises(TypeError, match="func must be callable"):
        reg.register("y", "a description", "not callable")
    with pytest.raises(ValueError, match="non-empty string"):
        reg.register("", "d", lambda: _ok())
    with pytest.raises(ValueError, match="not a valid subcommand token"):
        reg.register("bad name!", "d", lambda: _ok())

def test_check_run_wraps_raised_exception_but_not_bad_return_type():
    def raises():
        raise RuntimeError("boom")

    check = Check(name="explodes", description="d", func=raises)
    result = check.run()
    assert result.status is CheckStatus.FAIL
    assert "raised an exception" in result.message
    assert "RuntimeError: boom" in result.output

    def bad_return():
        return "not a CheckResult"

    bad_check = Check(name="bad", description="d", func=bad_return)
    # Unlike a raised exception, a bad return value is NOT converted to a
    # failing CheckResult -- it raises TypeError straight through (pinned).
    with pytest.raises(TypeError, match="must return a CheckResult"):
        bad_check.run()

# Subprocess tests against the real repository: real discovery, real checks.

@pytest.mark.timeout(300)
def test_cli_list_and_single_real_checks():
    """Real discovery, real checks, real subprocess -- but no live server.

    This used to end with a no-argument aggregate run asserting exit 0. That
    made a unit test assert the DEPLOYMENT's health, not the CLI's: the
    aggregate executes the ``check_live_*`` checks, which talk to the remote
    server over mTLS, and the CLI exits 1 if any single check fails. It duly
    failed while the Code Analysis server was being restarted mid-merge, and
    its 180s timeout was really measuring the network. The live battery is an
    explicit gate run against a deployment, not part of the unit suite.

    Nothing is lost by dropping it here: aggregate semantics (run every
    registered check, tally line, exit 1 on any failure) are pinned in
    process by ``test_no_argument_runs_all_checks_aggregate_exit``, and the
    subprocess path -- real pkgutil discovery, real check execution, real
    exit code -- is what this test still proves, against real static checks
    rather than stubs."""

    root = _repo_root()
    pp = _real_pythonpath(root)

    listed = _run_cli(["list"], cwd=root, pythonpath=pp)
    assert listed.returncode == 0, listed.stderr
    assert "check-boundary-check" in listed.stdout
    assert "check-recovery" in listed.stdout

    for name in ("check-boundary-check", "check-recovery"):
        single = _run_cli([name], cwd=root, pythonpath=pp)
        assert single.returncode == 0, single.stdout + single.stderr
        assert f"[PASS] {name}" in single.stdout

def test_cli_unknown_check_argparse_error():
    root = _repo_root()
    proc = _run_cli(["totally-unknown"], cwd=root, pythonpath=_real_pythonpath(root))
    assert proc.returncode == 2
    assert "invalid choice: 'totally-unknown'" in proc.stderr

def test_cli_argument_errors_extra_positional_and_bad_flag():
    root = _repo_root()
    pp = _real_pythonpath(root)
    extra = _run_cli(["list", "extra"], cwd=root, pythonpath=pp)
    assert extra.returncode == 2
    assert "unrecognized arguments" in extra.stderr

    flag = _run_cli(["--bogus-flag"], cwd=root, pythonpath=pp)
    assert flag.returncode == 2
    assert "unrecognized arguments" in flag.stderr

def test_check_recovery_resolves_tree_engine_from_the_installed_distribution():
    """Pin the PYTHONPATH reality AFTER ai-editor-tree-engine became its own
    distribution: 'src' on the path is no longer what makes tree_engine
    importable -- the installed distribution is. This test used to assert the
    opposite ("'.' alone is not enough"), which was true only while the engine
    shipped as a subpackage of the server.

    The engine resolving from site-packages rather than the checkout is the
    whole point of the split, so assert that too: a check must not silently
    exercise the working tree when the deployed artifact is what ships."""

    root = _repo_root()
    without_src = _run_cli(["list"], cwd=root, pythonpath=str(root))
    assert without_src.returncode == 0
    assert "check-recovery" in without_src.stdout
    assert "check-boundary-check" in without_src.stdout
    assert without_src.stderr == ""

    with_src = _run_cli(["list"], cwd=root, pythonpath=_real_pythonpath(root))
    assert with_src.returncode == 0
    assert "check-recovery" in with_src.stdout
    assert with_src.stderr == ""

    located = subprocess.run(
        [sys.executable, "-c", "import tree_engine.facade as f; print(f.__file__)"],
        cwd=str(root), env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True, text=True, check=True)
    engine_file = Path(located.stdout.strip())
    assert engine_file.is_file(), located.stdout
    assert root / "src" not in engine_file.parents, (
        f"tree_engine resolved from the checkout, not the installed distribution: {engine_file}")

# Subprocess tests against a throwaway pipeline/ copy: never touches real pipeline/checks/.

def test_discovery_picks_up_and_drops_new_check_file_automatically(pipeline_copy):
    checks_dir = pipeline_copy / "pipeline" / "checks"
    new_file = checks_dir / "check_extra_zz.py"
    new_file.write_text(
        "from pipeline import registry\n"
        "from pipeline.registry import CheckResult\n"
        "def check_extra_zz():\n"
        "    return CheckResult.ok('extra ran')\n"
        "registry.register('extra-zz', 'a dynamically added check', check_extra_zz)\n"
    )
    pp = _real_pythonpath(pipeline_copy)
    try:
        listed = _run_cli(["list"], cwd=pipeline_copy, pythonpath=pp)
        assert listed.returncode == 0, listed.stderr
        assert "extra-zz" in listed.stdout
        assert "a dynamically added check" in listed.stdout

        run = _run_cli(["extra-zz"], cwd=pipeline_copy, pythonpath=pp)
        assert run.returncode == 0, run.stderr
        assert "[PASS] extra-zz - extra ran" in run.stdout
    finally:
        new_file.unlink()

    listed_after = _run_cli(["list"], cwd=pipeline_copy, pythonpath=pp)
    assert "extra-zz" not in listed_after.stdout
    gone = _run_cli(["extra-zz"], cwd=pipeline_copy, pythonpath=pp)
    assert gone.returncode == 2
    assert "invalid choice" in gone.stderr
    real = {p.name for p in (_repo_root() / "pipeline" / "checks").glob("*.py")}
    assert "check_extra_zz.py" not in real  # real checks/ untouched

def test_discovery_resilience_broken_module_does_not_crash_cli(pipeline_copy):
    checks_dir = pipeline_copy / "pipeline" / "checks"
    broken = checks_dir / "check_broken_zz.py"
    broken.write_text("def broken(:\n    this is not valid python\n")
    pp = _real_pythonpath(pipeline_copy)

    proc = _run_cli(["list"], cwd=pipeline_copy, pythonpath=pp)
    assert proc.returncode == 0, proc.stderr
    assert (
        "pipeline: warning: failed to import check module "
        "'pipeline.checks.check_broken_zz'" in proc.stderr
    )
    assert "check-boundary-check" in proc.stdout
    assert "check-recovery" in proc.stdout

def test_list_mode_does_not_execute_side_effect_check(pipeline_copy):
    checks_dir = pipeline_copy / "pipeline" / "checks"
    marker = pipeline_copy / "side_effect_marker.txt"
    side_effect_check = checks_dir / "check_side_effect_zz.py"
    side_effect_check.write_text(
        "from pipeline import registry\n"
        "from pipeline.registry import CheckResult\n"
        f"MARKER = {str(marker)!r}\n"
        "def check_side_effect_zz():\n"
        "    open(MARKER, 'w').write('ran')\n"
        "    return CheckResult.ok('side effect performed')\n"
        "registry.register('side-effect-zz', 'has a side effect', check_side_effect_zz)\n"
    )
    pp = _real_pythonpath(pipeline_copy)

    listed = _run_cli(["list"], cwd=pipeline_copy, pythonpath=pp)
    assert listed.returncode == 0, listed.stderr
    assert "side-effect-zz" in listed.stdout
    assert not marker.exists()  # list must never execute a check

    run = _run_cli(["side-effect-zz"], cwd=pipeline_copy, pythonpath=pp)
    assert run.returncode == 0, run.stderr
    assert marker.exists()
    assert marker.read_text() == "ran"

def test_failing_check_yields_nonzero_exit_real_cli(pipeline_copy):
    checks_dir = pipeline_copy / "pipeline" / "checks"
    (checks_dir / "check_fails_zz.py").write_text(
        "from pipeline import registry\n"
        "from pipeline.registry import CheckResult\n"
        "def check_fails_zz():\n"
        "    return CheckResult.fail('deliberately broken')\n"
        "registry.register('fails-zz', 'always fails', check_fails_zz)\n"
    )
    # The aggregate run below executes EVERY discovered check. The live ones
    # talk to the deployed server over mTLS and take minutes, which is not
    # what this test is about -- it asserts that one failing check makes the
    # aggregate exit nonzero. Dropping them from the throwaway copy keeps the
    # test deterministic instead of dependent on remote availability: it used
    # to "pass" only because the remote server happened to be unreachable and
    # every live check failed instantly.
    for live in checks_dir.glob("check_live_*.py"):
        live.unlink()
    pp = _real_pythonpath(pipeline_copy)

    single = _run_cli(["fails-zz"], cwd=pipeline_copy, pythonpath=pp)
    assert single.returncode == 1
    assert "[FAIL] fails-zz - deliberately broken" in single.stdout

    aggregate = _run_cli([], cwd=pipeline_copy, pythonpath=pp)
    assert aggregate.returncode == 1
    assert "[FAIL] fails-zz - deliberately broken" in aggregate.stdout
    assert "checks passed" in aggregate.stdout
